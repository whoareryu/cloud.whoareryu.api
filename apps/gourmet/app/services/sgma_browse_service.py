"""SgmaRestaurant(테이블 ``restaurant``) 기반 브라우즈·카드 목록 헬퍼."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from apps.gourmet.app.data.category_topics import TopicDef
from apps.gourmet.app.data.restaurant_images import image_url_for_restaurant
from apps.gourmet.app.models.sgma_restaurant import SgmaRestaurant
from apps.gourmet.app.services.restaurant_location_service import distance_km_to_entity
from apps.gourmet.app.services.sgma_restaurant_service import classify_sgma_category

CATEGORY_LABEL_BY_SLUG: dict[str, str] = {
    "hansik": "한식",
    "ilsik": "일식",
    "jungsik": "중식",
    "yangsik": "양식",
    "asian": "아시안",
    "bunsik": "분식",
    "cafe-dessert": "카페·디저트",
    "bar": "바",
}


def sgma_category_of(r: SgmaRestaurant) -> tuple[str, str]:
    """앱 카테고리 슬러그·표시 라벨."""
    slug, inferred = classify_sgma_category(
        r.biz_mid_name, r.biz_minor_name, r.ksic_name
    )
    label = CATEGORY_LABEL_BY_SLUG.get(slug, inferred)
    return slug, label


def sgma_display_from_row(r: SgmaRestaurant) -> str:
    """상호 표시 문자열."""
    s, b = (r.store_name or "").strip(), (r.branch_name or "").strip()
    if b:
        return f"{s} ({b})"
    return s or "상호 미상"


def sgma_pick_description(r: SgmaRestaurant) -> str:
    addr = (r.road_address or r.parcel_address or "").strip()
    minor = (r.biz_minor_name or "").strip()
    bits = [p for p in (minor if minor else None, addr[:180] if addr else None) if p]
    if not bits:
        return minor or addr or "공공 상가 정보"
    return " · ".join(bits)[:260]


def score_sgma_for_topic(r: SgmaRestaurant, topic_slug: str) -> int:
    raw = f"{topic_slug}:{r.id}:{r.biz_number}:{r.store_name}"
    return int(hashlib.md5(raw.encode("utf-8")).hexdigest()[:8], 16)


def pick_sgmas(
    pool: list[SgmaRestaurant],
    topic_slug: str,
    *,
    limit: int,
) -> list[SgmaRestaurant]:
    if not pool:
        return []
    ranked = sorted(pool, key=lambda r: score_sgma_for_topic(r, topic_slug))
    n = min(limit, len(ranked))
    offset = score_sgma_for_topic(ranked[0], f"off-{topic_slug}") % max(len(ranked), 1)
    rotated = ranked[offset:] + ranked[:offset]
    return rotated[:n]


def trending_sgma_boost(pool: list[SgmaRestaurant]) -> list[SgmaRestaurant]:
    """조회 통계 없이 상대적 ‘관심’ 순 흉내 — 업소번호 해시."""

    def key(r: SgmaRestaurant) -> tuple[int, int]:
        h = hash(r.biz_number or str(r.id)) % 8192
        return (-abs(h), r.id)

    return sorted(pool, key=key)


def pick_mixed_sgma_by_category(
    pool: list[SgmaRestaurant],
    topic_slug: str,
    *,
    limit: int,
) -> list[SgmaRestaurant]:
    """주제 행 안에서 카테고리별로 균등에 가깝게."""
    if not pool:
        return []

    by_cat: dict[str, list[SgmaRestaurant]] = defaultdict(list)
    for r in pool:
        by_cat[sgma_category_of(r)[0]].append(r)

    ranked: dict[str, list[SgmaRestaurant]] = {
        cat: sorted(rs, key=lambda r: score_sgma_for_topic(r, topic_slug))
        for cat, rs in by_cat.items()
    }
    indices = {cat: 0 for cat in ranked}
    cats = list(ranked.keys())
    out: list[SgmaRestaurant] = []
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


def sort_sgmas_by_distance(
    rows: list[SgmaRestaurant],
    user_lat: float,
    user_lng: float,
) -> list[SgmaRestaurant]:
    return sorted(
        rows,
        key=lambda r: distance_km_to_entity(r, user_lat, user_lng),
    )


def sgmas_to_pick_items(
    rows: list[SgmaRestaurant],
    *,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> list[dict]:
    """API용 카드 목록 (시드 레스토랑과 동일 키, detail_href 없음)."""
    ordered = rows
    if user_lat is not None and user_lng is not None:
        ordered = sort_sgmas_by_distance(rows, user_lat, user_lng)

    items: list[dict] = []
    for i, r in enumerate(ordered, start=1):
        slug, label = sgma_category_of(r)
        nm = sgma_display_from_row(r)
        desc = sgma_pick_description(r)
        image_url = image_url_for_restaurant(nm, slug, desc)
        item: dict = {
            "rank": i,
            "id": r.id,
            "name": nm,
            "category_slug": slug,
            "category_label": label,
            "district": r.district or r.sigungu_name or "",
            "description": desc,
            "image_url": image_url,
            "view_count": 0,
        }
        if user_lat is not None and user_lng is not None:
            item["distance_km"] = round(
                distance_km_to_entity(r, user_lat, user_lng), 1
            )
        items.append(item)
    return items


def sgma_topic_row(
    topic: TopicDef,
    sgmas: list[SgmaRestaurant],
    *,
    user_lat: float | None = None,
    user_lng: float | None = None,
    link_title: bool = True,
) -> dict:
    return {
        "slug": topic.slug,
        "title": topic.title,
        "subtitle": topic.subtitle,
        "emoji": topic.emoji,
        "keywords": list(topic.keywords),
        "restaurants": sgmas_to_pick_items(sgmas, user_lat=user_lat, user_lng=user_lng),
        "link_title": link_title,
    }


def bounded_sgma_slice(
    db: Session,
    *,
    limit_rows: int = 10_000,
    rotation_salt: int = 0,
    day_ord: int | None = None,
    total_row_count: int | None = None,
) -> list[SgmaRestaurant]:
    """대량 ``restaurant`` 테이블용 — 매 요청 전행 로드 금지. 날짜·salt 로 윈도우 이동."""
    do = day_ord if day_ord is not None else date.today().toordinal()
    if total_row_count is not None:
        cnt = int(total_row_count)
    else:
        cnt = int(
            db.execute(select(func.count()).select_from(SgmaRestaurant)).scalar_one()
            or 0
        )
    if cnt == 0:
        return []
    n = min(limit_rows, cnt)
    span = cnt - n
    off = ((do * 79_691 + rotation_salt * 3_961) % (span + 1)) if span > 0 else 0
    return list(
        db.execute(
            select(SgmaRestaurant).order_by(SgmaRestaurant.id).offset(off).limit(n)
        )
        .scalars()
        .all()
    )


SGMA_TEXT_SEARCH_COLUMNS = (
    SgmaRestaurant.store_name,
    SgmaRestaurant.branch_name,
    SgmaRestaurant.biz_mid_name,
    SgmaRestaurant.biz_minor_name,
    SgmaRestaurant.ksic_name,
    SgmaRestaurant.district,
    SgmaRestaurant.sigungu_name,
    SgmaRestaurant.road_address,
    SgmaRestaurant.parcel_address,
)


def fetch_sgma_text_search_candidates(
    db: Session,
    *,
    patterns: list[str],
    limit: int = 1_600,
) -> list[SgmaRestaurant]:
    """ILIKE 후보만 제한 행수로 로드."""
    uniq: list[str] = []
    for p in patterns:
        if p and p not in uniq:
            uniq.append(p)
        if len(uniq) >= 14:
            break
    if not uniq:
        return bounded_sgma_slice(db, limit_rows=min(6_000, limit * 4))
    parts = [or_(*[col.ilike(p) for col in SGMA_TEXT_SEARCH_COLUMNS]) for p in uniq]
    cond = or_(*parts) if len(parts) > 1 else parts[0]
    rows = list(
        db.execute(select(SgmaRestaurant).where(cond).limit(limit)).scalars().all()
    )
    if not rows:
        return bounded_sgma_slice(db, limit_rows=min(8_000, limit * 5))
    return rows


# ``gourmet_router`` 상세 등에서 이름만 필요할 때
def sgma_restaurant_name_for_views(db: Session, store_id: int) -> str | None:
    r = db.get(SgmaRestaurant, store_id)
    return sgma_display_from_row(r) if r else None
