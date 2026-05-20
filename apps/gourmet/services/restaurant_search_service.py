"""검색어 기반 맛집 추천."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from apps.gourmet.data.category_topics import (
    COMMON_TOPICS,
    CATEGORY_EXTRA_TOPICS,
    TopicDef,
    filter_topics_by_query,
)
from apps.gourmet.data.search_keywords import (
    expand_search_terms,
    topic_slugs_for_query,
)
from apps.gourmet.models.restaurant import Restaurant
from apps.gourmet.services.home_browse_service import _pick_mixed_by_category
from apps.gourmet.services.today_picks_service import ensure_restaurants_seeded

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 24


def _all_topics() -> list[TopicDef]:
    topics = list(COMMON_TOPICS)
    for extras in CATEGORY_EXTRA_TOPICS.values():
        topics.extend(extras)
    return topics


def _restaurant_haystack(r: Restaurant) -> str:
    parts = [
        r.name,
        r.description,
        r.district,
        r.category_label,
        r.category_slug,
        r.address or "",
    ]
    for m in r.menu_items or []:
        if isinstance(m, dict):
            parts.append(str(m.get("name", "")))
            parts.append(str(m.get("note", "")))
    return " ".join(parts).lower()


def _topic_applies(topic: TopicDef, restaurant: Restaurant) -> bool:
    if topic.category_slugs and restaurant.category_slug not in topic.category_slugs:
        return False
    return True


def _score_restaurant(
    r: Restaurant,
    terms: list[str],
    *,
    primary: str,
    boosted_slugs: set[str],
) -> int:
    hay = _restaurant_haystack(r)
    score = 0
    for term in terms:
        if term in hay:
            score += 20 if term == primary else 6
    topics_by_slug = {t.slug: t for t in _all_topics()}
    for slug in boosted_slugs:
        topic = topics_by_slug.get(slug)
        if topic and _topic_applies(topic, r):
            score += 12
    vc = r.view_stat.view_count if r.view_stat else 0
    score += min(vc, 10)
    return score


def _build_summary(q: str, terms: list[str], topics: list[TopicDef], count: int) -> str:
    if topics:
        titles = " · ".join(f"{t.emoji} {t.title}" for t in topics[:2])
        return f'"{q}" — {titles} 등 {count}곳'
    if "여름" in terms or "여름" in q:
        return f'"{q}" — 여름·시원한 메뉴 맛집 {count}곳'
    if "해장" in terms or "해장" in q:
        return f'"{q}" — 해장·국물 맛집 {count}곳'
    return f'"{q}" 검색 결과 {count}곳'


def search_restaurants(db: Session, q: str) -> dict:
    """검색어에 맞는 식당 목록과 매칭 주제."""
    raw = q.strip()
    if not raw:
        return {
            "query": "",
            "summary": "",
            "matched_topics": [],
            "restaurants": [],
        }

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

    terms = expand_search_terms(raw)
    primary = raw.lower()
    boosted_slugs = set(topic_slugs_for_query(raw, terms))
    matched_topics = filter_topics_by_query(_all_topics(), raw)
    for t in matched_topics:
        boosted_slugs.add(t.slug)

    scored: list[tuple[Restaurant, int]] = []
    for r in all_restaurants:
        s = _score_restaurant(r, terms, primary=primary, boosted_slugs=boosted_slugs)
        if s > 0:
            scored.append((r, s))

    picked: list[Restaurant] = []
    seen: set[int] = set()

    if scored:
        scored.sort(key=lambda x: (-x[1], x[0].id))
        for r, _ in scored:
            if r.id in seen:
                continue
            seen.add(r.id)
            picked.append(r)
            if len(picked) >= SEARCH_LIMIT:
                break

    if len(picked) < SEARCH_LIMIT and matched_topics:
        for topic in matched_topics[:4]:
            pool = [
                r
                for r in all_restaurants
                if _topic_applies(topic, r) and r.id not in seen
            ]
            if not pool:
                pool = [r for r in all_restaurants if r.id not in seen]
            extra = _pick_mixed_by_category(pool, topic.slug, limit=8)
            for r in extra:
                if r.id in seen:
                    continue
                seen.add(r.id)
                picked.append(r)
                if len(picked) >= SEARCH_LIMIT:
                    break
            if len(picked) >= SEARCH_LIMIT:
                break

    items = []
    for i, r in enumerate(picked, start=1):
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

    summary = _build_summary(raw, terms, matched_topics, len(items))
    logger.info("[gourmet] search q=%s — %s건", raw, len(items))

    return {
        "query": raw,
        "summary": summary,
        "matched_topics": [
            {
                "slug": t.slug,
                "title": t.title,
                "emoji": t.emoji,
            }
            for t in matched_topics[:6]
        ],
        "restaurants": items,
    }
