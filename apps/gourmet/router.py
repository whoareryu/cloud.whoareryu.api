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
