"""메인 홈 — 주제당 전 장르 식당을 한 행에 섞어서 반환."""

from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from apps.gourmet.data.category_topics import (
    COMMON_TOPICS,
    filter_topics_by_query,
)
from apps.gourmet.models.restaurant import Restaurant
from apps.gourmet.services.category_browse_service import (
    _pick_restaurants,
    _score_restaurant,
    _topic_row,
    _trending_boost,
)
from apps.gourmet.services.today_picks_service import ensure_restaurants_seeded

logger = logging.getLogger(__name__)

HOME_PICKS_PER_TOPIC = 10
MAX_HOME_TOPICS = 16
# 메인 홈에서 한 식당이 등장할 수 있는 최대 주제 수
MAX_TOPICS_PER_RESTAURANT = 2


def _pick_mixed_by_category(
    pool: list[Restaurant],
    topic_slug: str,
    *,
    limit: int = HOME_PICKS_PER_TOPIC,
) -> list[Restaurant]:
    """한 주제 행에 여러 category_slug 식당이 골고루 들어가도록."""
    if not pool:
        return []

    by_cat: dict[str, list[Restaurant]] = defaultdict(list)
    for r in pool:
        by_cat[r.category_slug].append(r)

    ranked: dict[str, list[Restaurant]] = {
        cat: sorted(rs, key=lambda r: _score_restaurant(r, topic_slug))
        for cat, rs in by_cat.items()
    }
    indices = {cat: 0 for cat in ranked}
    cats = list(ranked.keys())
    out: list[Restaurant] = []
    seen_ids: set[int] = set()

    while len(out) < limit and cats:
        progressed = False
        for cat in cats:
            lst = ranked[cat]
            idx = indices[cat]
            while idx < len(lst):
                r = lst[idx]
                indices[cat] = idx + 1
                idx += 1
                if r.id not in seen_ids:
                    out.append(r)
                    seen_ids.add(r.id)
                    progressed = True
                    break
            if len(out) >= limit:
                break
        if not progressed:
            break

    return out


def _eligible_for_topic(
    pool: list[Restaurant],
    usage_count: dict[int, int],
) -> list[Restaurant]:
    """이미 충분히 배정된 식당은 제외."""
    return [
        r
        for r in pool
        if usage_count.get(r.id, 0) < MAX_TOPICS_PER_RESTAURANT
    ]


def get_home_browse(db: Session, *, q: str | None = None) -> list[dict]:
    ensure_restaurants_seeded(db)
    all_restaurants = list(
        db.execute(
            select(Restaurant)
            .options(joinedload(Restaurant.view_stat))
            .order_by(Restaurant.id)
        )
        .scalars()
        .all()
    )
    if not all_restaurants:
        return []

    topics = list(COMMON_TOPICS[:MAX_HOME_TOPICS])
    if q:
        topics = filter_topics_by_query(topics, q)

    rows: list[dict] = []
    topic_usage_count: dict[int, int] = defaultdict(int)

    for topic in topics:
        eligible = _eligible_for_topic(all_restaurants, topic_usage_count)
        if not eligible:
            continue

        if topic.slug == "trending-now":
            pool = _trending_boost(eligible)
            picks = _pick_restaurants(pool, topic.slug, limit=HOME_PICKS_PER_TOPIC)
        else:
            picks = _pick_mixed_by_category(
                eligible, topic.slug, limit=HOME_PICKS_PER_TOPIC
            )
        if not picks:
            continue

        for r in picks:
            topic_usage_count[r.id] += 1

        rows.append(_topic_row(topic, picks))

    logger.info(
        "[gourmet] home-browse — %s개 주제 행 (식당당 최대 %s주제)",
        len(rows),
        MAX_TOPICS_PER_RESTAURANT,
    )
    return rows
