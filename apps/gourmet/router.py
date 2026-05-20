import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.database import DATABASE_INIT_ERROR, get_sync_db
from apps.gourmet.data.category_topics import ALL_CATEGORY_SLUGS
from apps.gourmet.services.category_browse_service import (
    get_category_browse,
    list_topic_catalog,
)
from apps.gourmet.services.home_browse_service import get_home_browse
from apps.gourmet.services.restaurant_search_service import search_restaurants
from apps.gourmet.services.today_picks_service import get_today_picks
from apps.gourmet.services.view_stat_service import (
    get_view_stat,
    list_view_stats,
    record_restaurant_view,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gourmet", tags=["gourmet"])


class TodayPickItem(BaseModel):
    rank: int
    id: int
    name: str
    category_slug: str
    category_label: str
    district: str
    description: str
    image_url: str
    view_count: int = 0


class RestaurantViewStatResponse(BaseModel):
    restaurant_id: int
    restaurant_name: str
    view_count: int
    first_viewed_at: str | None
    last_viewed_at: str | None


class RecordViewResponse(BaseModel):
    restaurant_id: int
    view_count: int
    message: str = "조회가 기록되었습니다."


class MenuItemResponse(BaseModel):
    name: str
    price: int
    note: str = ""


class RestaurantDetailResponse(BaseModel):
    id: int
    name: str
    category_slug: str
    category_label: str
    district: str
    description: str
    image_url: str
    view_count: int = 0
    closed_weekdays: list[int] = []
    closed_weekdays_label: str = ""
    address: str = ""
    opening_hours: str = ""
    phone: str | None = None
    instagram_url: str | None = None
    reservation_available: bool = False
    reservation_note: str = ""
    menu_items: list[MenuItemResponse] = []


WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")


def _format_closed_weekdays(closed: list[int]) -> str:
    if not closed:
        return "연중무휴 (휴무 정보 없음)"
    days = [WEEKDAY_KO[d] for d in sorted(closed) if 0 <= d <= 6]
    return f"매주 {', '.join(days)}요일 휴무"


class TodayPicksResponse(BaseModel):
    title: str = "오늘의 맛집"
    date: str
    picks_per_category_min: int = 2
    picks_per_category_max: int = 3
    picks: list[TodayPickItem]


class TopicMeta(BaseModel):
    slug: str
    title: str
    subtitle: str
    emoji: str
    keywords: list[str] = []


class TopicRowResponse(BaseModel):
    slug: str
    title: str
    subtitle: str
    emoji: str
    keywords: list[str] = []
    restaurants: list[TodayPickItem]
    category_slug: str | None = None
    category_label: str | None = None


class HomeBrowseResponse(BaseModel):
    query: str | None = None
    topic_count: int
    topics: list[TopicRowResponse]


class SearchMatchedTopic(BaseModel):
    slug: str
    title: str
    emoji: str


class RestaurantSearchResponse(BaseModel):
    query: str
    summary: str
    matched_topics: list[SearchMatchedTopic] = []
    restaurants: list[TodayPickItem]


class CategoryBrowseResponse(BaseModel):
    category_slug: str
    category_label: str
    query: str | None = None
    topic_count: int
    topics: list[TopicRowResponse]


@router.get("/categories/{category_slug}/browse", response_model=CategoryBrowseResponse)
def read_category_browse(
    category_slug: str,
    q: str | None = None,
    db: Session = Depends(get_sync_db),
):
    """카테고리별 주제 행 — 넷플릭스 스타일 맛집 안내."""
    if category_slug not in ALL_CATEGORY_SLUGS:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    try:
        slug, label, rows = get_category_browse(db, category_slug, q=q)
    except Exception:
        logger.exception("[gourmet] category browse 실패 slug=%s", category_slug)
        raise HTTPException(
            status_code=500,
            detail="카테고리 맛집 목록을 불러오지 못했습니다.",
        ) from None
    topics = [
        TopicRowResponse(
            slug=r["slug"],
            title=r["title"],
            subtitle=r["subtitle"],
            emoji=r["emoji"],
            keywords=r["keywords"],
            restaurants=[TodayPickItem(**item) for item in r["restaurants"]],
        )
        for r in rows
    ]
    return CategoryBrowseResponse(
        category_slug=slug,
        category_label=label,
        query=q,
        topic_count=len(topics),
        topics=topics,
    )


@router.get("/home-browse", response_model=HomeBrowseResponse)
def read_home_browse(
    q: str | None = None,
    db: Session = Depends(get_sync_db),
):
    """메인 — 전 카테고리 주제 추천을 섞어서 반환."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    try:
        rows = get_home_browse(db, q=q)
    except Exception:
        logger.exception("[gourmet] home-browse 실패")
        raise HTTPException(
            status_code=500,
            detail="홈 맛집 목록을 불러오지 못했습니다.",
        ) from None
    topics = [
        TopicRowResponse(
            slug=r["slug"],
            title=r["title"],
            subtitle=r["subtitle"],
            emoji=r["emoji"],
            keywords=r["keywords"],
            restaurants=[TodayPickItem(**item) for item in r["restaurants"]],
            category_slug=r.get("category_slug"),
            category_label=r.get("category_label"),
        )
        for r in rows
    ]
    return HomeBrowseResponse(query=q, topic_count=len(topics), topics=topics)


@router.get("/search", response_model=RestaurantSearchResponse)
def read_restaurant_search(
    q: str,
    db: Session = Depends(get_sync_db),
):
    """검색어에 맞는 맛집 추천 (메뉴·설명·주제 키워드)."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    if not q.strip():
        return RestaurantSearchResponse(
            query="",
            summary="",
            matched_topics=[],
            restaurants=[],
        )
    try:
        result = search_restaurants(db, q)
    except Exception:
        logger.exception("[gourmet] search 실패 q=%s", q)
        raise HTTPException(
            status_code=500,
            detail="검색 결과를 불러오지 못했습니다.",
        ) from None
    return RestaurantSearchResponse(
        query=result["query"],
        summary=result["summary"],
        matched_topics=[SearchMatchedTopic(**t) for t in result["matched_topics"]],
        restaurants=[TodayPickItem(**item) for item in result["restaurants"]],
    )


@router.get("/categories/{category_slug}/topics", response_model=list[TopicMeta])
def read_category_topic_catalog(category_slug: str):
    """주제 검색용 카탈로그."""
    if category_slug not in ALL_CATEGORY_SLUGS:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    return [TopicMeta(**t) for t in list_topic_catalog(category_slug)]


@router.get("/today-picks", response_model=TodayPicksResponse)
def read_today_picks(db: Session = Depends(get_sync_db)):
    """오늘의 맛집 — 카테고리별 2~3곳, 전날·유사·휴무일 제외."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(
            status_code=503,
            detail="데이터베이스에 연결할 수 없습니다.",
        )
    try:
        pick_date, restaurants = get_today_picks(db)
    except Exception:
        logger.exception("[gourmet] today-picks 생성 실패")
        raise HTTPException(
            status_code=500,
            detail="오늘의 맛집 목록을 불러오지 못했습니다.",
        ) from None

    picks = []
    for i, r in enumerate(restaurants, start=1):
        vc = r.view_stat.view_count if r.view_stat else 0
        picks.append(
            TodayPickItem(
                rank=i,
                id=r.id,
                name=r.name,
                category_slug=r.category_slug,
                category_label=r.category_label,
                district=r.district,
                description=r.description,
                image_url=r.image_url,
                view_count=vc,
            )
        )
    return TodayPicksResponse(date=pick_date.isoformat(), picks=picks)


@router.get("/restaurants/{restaurant_id}", response_model=RestaurantDetailResponse)
def read_restaurant_detail(restaurant_id: int, db: Session = Depends(get_sync_db)):
    """매장 상세 정보."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    from apps.gourmet.models.restaurant import Restaurant
    from apps.gourmet.services.restaurant_profile_service import sync_restaurant_profiles

    sync_restaurant_profiles(db)
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="식당을 찾을 수 없습니다.")
    stat = get_view_stat(db, restaurant_id)
    closed = list(restaurant.closed_weekdays or [])
    raw_menu = restaurant.menu_items or []
    menu_items = [
        MenuItemResponse(
            name=m.get("name", ""),
            price=int(m.get("price", 0)),
            note=m.get("note") or "",
        )
        for m in raw_menu
        if isinstance(m, dict) and m.get("name")
    ]
    return RestaurantDetailResponse(
        id=restaurant.id,
        name=restaurant.name,
        category_slug=restaurant.category_slug,
        category_label=restaurant.category_label,
        district=restaurant.district,
        description=restaurant.description,
        image_url=restaurant.image_url,
        view_count=stat.view_count if stat else 0,
        closed_weekdays=closed,
        closed_weekdays_label=_format_closed_weekdays(closed),
        address=restaurant.address or "",
        opening_hours=restaurant.opening_hours or "",
        phone=restaurant.phone,
        instagram_url=restaurant.instagram_url,
        reservation_available=bool(restaurant.reservation_available),
        reservation_note=restaurant.reservation_note or "",
        menu_items=menu_items,
    )


@router.post("/restaurants/{restaurant_id}/view", response_model=RecordViewResponse)
def post_restaurant_view(restaurant_id: int, db: Session = Depends(get_sync_db)):
    """매장 상세·카드 조회 시 호출 — view_count +1."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    try:
        stat = record_restaurant_view(db, restaurant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception:
        logger.exception("[gourmet] 조회 기록 실패 restaurant_id=%s", restaurant_id)
        raise HTTPException(status_code=500, detail="조회 기록에 실패했습니다.") from None
    return RecordViewResponse(restaurant_id=restaurant_id, view_count=stat.view_count)


@router.get("/restaurants/{restaurant_id}/views", response_model=RestaurantViewStatResponse)
def read_restaurant_views(restaurant_id: int, db: Session = Depends(get_sync_db)):
    """매장별 누적 조회 수 조회."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    from apps.gourmet.models.restaurant import Restaurant

    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="식당을 찾을 수 없습니다.")
    stat = get_view_stat(db, restaurant_id)
    if stat is None:
        return RestaurantViewStatResponse(
            restaurant_id=restaurant_id,
            restaurant_name=restaurant.name,
            view_count=0,
            first_viewed_at=None,
            last_viewed_at=None,
        )
    return RestaurantViewStatResponse(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant.name,
        view_count=stat.view_count,
        first_viewed_at=stat.first_viewed_at.isoformat() if stat.first_viewed_at else None,
        last_viewed_at=stat.last_viewed_at.isoformat() if stat.last_viewed_at else None,
    )


@router.get("/view-stats", response_model=list[RestaurantViewStatResponse])
def read_top_view_stats(db: Session = Depends(get_sync_db), limit: int = 20):
    """관심도 상위 매장 (조회 수 순)."""
    if DATABASE_INIT_ERROR:
        raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
    rows = list_view_stats(db, limit=min(limit, 100))
    return [
        RestaurantViewStatResponse(
            restaurant_id=r.id,
            restaurant_name=r.name,
            view_count=s.view_count,
            first_viewed_at=s.first_viewed_at.isoformat() if s.first_viewed_at else None,
            last_viewed_at=s.last_viewed_at.isoformat() if s.last_viewed_at else None,
        )
        for r, s in rows
    ]
