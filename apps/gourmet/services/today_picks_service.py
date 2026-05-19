"""오늘의 맛집 — 카테고리별 2~3곳, 영업일·전날 중복·유사명 제외."""

from __future__ import annotations

import datetime
import logging
import random
from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from apps.gourmet.data.seed_restaurants import SEED_RESTAURANTS, normalize_name_key
from apps.gourmet.models.daily_pick import DailyPick
from apps.gourmet.models.restaurant import Restaurant

logger = logging.getLogger(__name__)

# 네비게이션 카테고리 순서
CATEGORY_SLUGS: tuple[str, ...] = (
    "hansik",
    "ilsik",
    "jungsik",
    "yangsik",
    "asian",
    "bunsik",
    "cafe-dessert",
    "bar",
)

PICKS_PER_CATEGORY_MIN = 2
PICKS_PER_CATEGORY_MAX = 3
SIMILARITY_THRESHOLD = 0.72


def _is_open_on(restaurant: Restaurant, day: datetime.date) -> bool:
    closed = restaurant.closed_weekdays or []
    return day.weekday() not in closed


def _names_similar(a: str, b: str) -> bool:
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD


def _is_similar_to_yesterday(restaurant: Restaurant, yesterday_rows: list[Restaurant]) -> bool:
    for prev in yesterday_rows:
        if restaurant.id == prev.id:
            return True
        if restaurant.name_key == prev.name_key:
            return True
        if _names_similar(restaurant.name_key, prev.name_key):
            return True
        if _names_similar(normalize_name_key(restaurant.name), normalize_name_key(prev.name)):
            return True
    return False


def _is_similar_to_chosen(restaurant: Restaurant, chosen: list[Restaurant]) -> bool:
    for other in chosen:
        if restaurant.id == other.id:
            return True
        if restaurant.name_key == other.name_key:
            return True
        if _names_similar(restaurant.name_key, other.name_key):
            return True
    return False


def seed_restaurants_if_empty(db: Session) -> None:
    count = db.execute(select(func.count(Restaurant.id))).scalar_one()
    if count > 0:
        return
    for row in SEED_RESTAURANTS:
        db.add(
            Restaurant(
                name=row["name"],
                name_key=row["name_key"],
                category_slug=row["category_slug"],
                category_label=row["category_label"],
                district=row["district"],
                description=row["description"],
                image_url=row["image_url"],
                closed_weekdays=list(row["closed_weekdays"]),
            )
        )
    db.commit()
    logger.info("[gourmet] restaurants 시드 %s건 INSERT", len(SEED_RESTAURANTS))


def _yesterday_restaurants(db: Session, today: datetime.date) -> list[Restaurant]:
    yesterday = today - datetime.timedelta(days=1)
    picks = db.execute(
        select(DailyPick)
        .options(_pick_options())
        .where(DailyPick.pick_date == yesterday)
        .order_by(DailyPick.rank)
    ).scalars().all()
    return [p.restaurant for p in picks if p.restaurant]


def _get_existing_picks(db: Session, today: datetime.date) -> list[DailyPick]:
    return list(
        db.execute(
            select(DailyPick)
            .options(
                joinedload(DailyPick.restaurant).joinedload(Restaurant.view_stat)
            )
            .where(DailyPick.pick_date == today)
            .order_by(DailyPick.rank)
        )
        .scalars()
        .all()
    )


def _pick_options():
    return joinedload(DailyPick.restaurant).joinedload(Restaurant.view_stat)


def _count_by_category(picks: list[DailyPick]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for pick in picks:
        if pick.restaurant:
            counts[pick.restaurant.category_slug] += 1
    return counts


def _picks_layout_valid(picks: list[DailyPick]) -> bool:
    """카테고리마다 2~3곳인지 확인."""
    if not picks:
        return False
    counts = _count_by_category(picks)
    for slug in CATEGORY_SLUGS:
        n = counts.get(slug, 0)
        if n < PICKS_PER_CATEGORY_MIN or n > PICKS_PER_CATEGORY_MAX:
            return False
    return True


def _pick_count_for_pool(pool_size: int) -> int:
    """가능한 만큼 3곳, 최소 2곳(부족 시 가능한 수)."""
    if pool_size >= PICKS_PER_CATEGORY_MAX:
        return PICKS_PER_CATEGORY_MAX
    if pool_size >= PICKS_PER_CATEGORY_MIN:
        return pool_size
    return pool_size


def _generate_picks(db: Session, today: datetime.date) -> list[DailyPick]:
    all_restaurants = list(db.execute(select(Restaurant)).scalars().all())
    yesterday_list = _yesterday_restaurants(db, today)
    already_chosen: list[Restaurant] = []

    by_category: dict[str, list[Restaurant]] = defaultdict(list)
    for r in all_restaurants:
        by_category[r.category_slug].append(r)

    rank = 0
    for slug in CATEGORY_SLUGS:
        pool = by_category.get(slug, [])
        eligible = [
            r
            for r in pool
            if _is_open_on(r, today)
            and not _is_similar_to_yesterday(r, yesterday_list)
            and not _is_similar_to_chosen(r, already_chosen)
        ]

        if len(eligible) < PICKS_PER_CATEGORY_MIN:
            eligible = [
                r
                for r in pool
                if _is_open_on(r, today)
                and r.id not in {p.id for p in yesterday_list}
                and not _is_similar_to_chosen(r, already_chosen)
            ]

        if len(eligible) < PICKS_PER_CATEGORY_MIN:
            eligible = [r for r in pool if _is_open_on(r, today)]

        n_pick = _pick_count_for_pool(len(eligible))
        random.shuffle(eligible)
        chosen_for_cat = eligible[:n_pick]

        for restaurant in chosen_for_cat:
            rank += 1
            db.add(
                DailyPick(
                    pick_date=today,
                    restaurant_id=restaurant.id,
                    rank=rank,
                )
            )
            already_chosen.append(restaurant)

        logger.info(
            "[gourmet] %s — %s곳 추천 (후보 %s곳)",
            slug,
            len(chosen_for_cat),
            len(pool),
        )

    db.commit()
    return _get_existing_picks(db, today)


def get_today_picks(
    db: Session, today: datetime.date | None = None
) -> tuple[datetime.date, list[Restaurant]]:
    """오늘의 맛집 — 카테고리별 2~3곳."""
    seed_restaurants_if_empty(db)
    today = today or datetime.date.today()

    existing = _get_existing_picks(db, today)
    if not _picks_layout_valid(existing):
        if existing:
            for pick in existing:
                db.delete(pick)
            db.commit()
        existing = _generate_picks(db, today)

    restaurants = [p.restaurant for p in existing if p.restaurant]
    return today, restaurants


def expected_pick_count() -> int:
    """최대 카테고리 수 × 3."""
    return len(CATEGORY_SLUGS) * PICKS_PER_CATEGORY_MAX
