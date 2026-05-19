"""카테고리별 주제 행(넷플릭스 스타일) — 식당 배치."""

from __future__ import annotations

import hashlib
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from apps.gourmet.data.category_topics import (
    TopicDef,
    filter_topics_by_query,
    topics_for_category,
)
from apps.gourmet.models.restaurant import Restaurant
from apps.gourmet.services.today_picks_service import seed_restaurants_if_empty

logger = logging.getLogger(__name__)

PICKS_PER_TOPIC = 8


def _score_restaurant(restaurant: Restaurant, topic_slug: str) -> int:
    raw = f"{topic_slug}:{restaurant.id}:{restaurant.name_key}"
    return int(hashlib.md5(raw.encode()).hexdigest()[:8], 16)


def _pick_restaurants(
    pool: list[Restaurant],
    topic_slug: str,
    *,
    limit: int = PICKS_PER_TOPIC,
) -> list[Restaurant]:
    if not pool:
        return []
    ranked = sorted(pool, key=lambda r: _score_restaurant(r, topic_slug))
    n = min(limit, len(ranked))
    # 주제마다 시작 오프셋을 달리해 행 간 겹침을 줄임
    offset = _score_restaurant(ranked[0], f"off-{topic_slug}") % max(len(ranked), 1)
    rotated = ranked[offset:] + ranked[:offset]
    return rotated[:n]


def _trending_boost(pool: list[Restaurant]) -> list[Restaurant]:
    """view_count 높은 순, 동점이면 id."""

    def key(r: Restaurant) -> tuple[int, int]:
        vc = r.view_stat.view_count if r.view_stat else 0
        return (-vc, r.id)

    return sorted(pool, key=key)


def get_category_browse(
    db: Session,
    category_slug: str,
    *,
    q: str | None = None,
) -> tuple[str, str, list[dict]]:
    """
  Returns (category_slug, category_label, rows).
  Each row: topic fields + restaurants list.
    """
    seed_restaurants_if_empty(db)
    pool = list(
        db.execute(
            select(Restaurant)
            .options(joinedload(Restaurant.view_stat))
            .where(Restaurant.category_slug == category_slug)
            .order_by(Restaurant.id)
        )
        .scalars()
        .all()
    )
    if not pool:
        logger.warning("[gourmet] browse — category=%s 식당 없음", category_slug)
        return category_slug, category_slug, []

    label = pool[0].category_label
    topics = topics_for_category(category_slug)
    if q:
        topics = filter_topics_by_query(topics, q)

    rows: list[dict] = []
    for topic in topics:
        if topic.slug == "trending-now":
            picks = _pick_restaurants(_trending_boost(pool), topic.slug, limit=PICKS_PER_TOPIC)
        else:
            picks = _pick_restaurants(pool, topic.slug, limit=PICKS_PER_TOPIC)
        rows.append(_topic_row(topic, picks))

    return category_slug, label, rows


def _topic_row(topic: TopicDef, restaurants: list[Restaurant]) -> dict:
    items = []
    for i, r in enumerate(restaurants, start=1):
        vc = r.view_stat.view_count if r.view_stat else 0
        items.append(
            {
                "rank": i,
                "id": r.id,
                "name": r.name,
                "category_slug": r.category_slug,
                "category_label": r.category_label,
                "district": r.district,
                "description": r.description,
                "image_url": r.image_url,
                "view_count": vc,
            }
        )
    return {
        "slug": topic.slug,
        "title": topic.title,
        "subtitle": topic.subtitle,
        "emoji": topic.emoji,
        "keywords": list(topic.keywords),
        "restaurants": items,
    }


def list_topic_catalog(category_slug: str) -> list[dict]:
    """검색 힌트용 전체 주제 목록 (식당 없이)."""
    return [
        {
            "slug": t.slug,
            "title": t.title,
            "subtitle": t.subtitle,
            "emoji": t.emoji,
            "keywords": list(t.keywords),
        }
        for t in topics_for_category(category_slug)
    ]
