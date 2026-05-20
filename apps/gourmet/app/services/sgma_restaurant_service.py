"""소상공인 상가 공공 CSV → ``restaurant`` 테이블(SgmaRestaurant) 적재 및 홈 노출 보조."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from apps.gourmet.app.data.restaurant_images import image_url_for_restaurant
from apps.gourmet.app.models.sgma_restaurant import SgmaRestaurant

logger = logging.getLogger(__name__)

_CHUNK = 1200


def classify_sgma_category(
    biz_mid_name: str, biz_minor_name: str, ksic_name: str
) -> tuple[str, str]:
    """상권 업종 문자열을 앱 ``category_slug``·라벨로 매핑."""
    text = f"{biz_mid_name} {biz_minor_name} {ksic_name}"

    def has(*keys: str) -> bool:
        return any(k in text for k in keys)

    if has("카페", "커피", "디저트", "베이커리", "제과", "빵"):
        return "cafe-dessert", "카페·디저트"
    if has("주점", "요리 주점", "호프"):
        return "bar", "바"
    if has("일식", "스시", "사시미", "라멘", "돈까스", "돈카츠", "우동", "초밥", "오코노미"):
        return "ilsik", "일식"
    if has("중식", "중화", "중국", "짜장", "짬뽕", "마라", "딤섬", "양꼬치"):
        return "jungsik", "중식"
    if has("양식", "파스타", "피자", "스테이크", "버거", "패스트푸드", "패밀리"):
        return "yangsik", "양식"
    if has("태국", "베트남", "태국식", "쌀국수", "포 ", "반미", "인도", "멕시코", "타코"):
        return "asian", "아시안"
    if has("분식", "떡볶이", "김밥", "어묵"):
        return "bunsik", "분식"
    return "hansik", "한식"


def _display_name(store_name: str, branch_name: str) -> str:
    s, b = (store_name or "").strip(), (branch_name or "").strip()
    if b:
        return f"{s} ({b})"
    return s or b or "상호 미상"


def _district(sigungu: str, admin_dong: str, legal_dong: str) -> str:
    gu = (sigungu or "").strip()
    dong = ((admin_dong or "").strip() or (legal_dong or "").strip())
    parts = [p for p in (gu, dong) if p]
    return " ".join(parts) if parts else ""


def _safe_float(cell: str) -> float | None:
    t = (cell or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def sync_sgma_restaurants_from_csv(db: Session, csv_path: Path) -> tuple[int, int]:
    """기존 ``restaurant`` 행 삭제 후 CSV 전건 재적재."""
    deleted = db.execute(delete(SgmaRestaurant)).rowcount or 0
    db.commit()
    logger.info("[gourmet sgma] restaurant 테이블 비움 (삭제 행수=%s)", deleted)

    if not csv_path.is_file():
        raise FileNotFoundError(str(csv_path))

    inserted = 0
    seen_biz: set[str] = set()
    pending: list[SgmaRestaurant] = []

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            biz = (row.get("상가업소번호") or "").strip()
            if not biz:
                continue
            if biz in seen_biz:
                continue
            seen_biz.add(biz)

            mid_n = row.get("상권업종중분류명") or ""
            min_n = row.get("상권업종소분류명") or ""
            ksic_n = row.get("표준산업분류명") or ""

            lat = _safe_float(row.get("위도") or "")
            lng = _safe_float(row.get("경도") or "")
            postal = (
                row.get("신우편번호") or row.get("구우편번호") or ""
            ).strip()

            sg = SgmaRestaurant(
                biz_number=biz,
                store_name=(row.get("상호명") or "").strip() or "미상",
                branch_name=(row.get("지점명") or "").strip(),
                biz_major_code=(row.get("상권업종대분류코드") or "").strip(),
                biz_major_name=(row.get("상권업종대분류명") or "").strip(),
                biz_mid_code=(row.get("상권업종중분류코드") or "").strip(),
                biz_mid_name=mid_n.strip(),
                biz_minor_code=(row.get("상권업종소분류코드") or "").strip(),
                biz_minor_name=min_n.strip(),
                ksic_code=(row.get("표준산업분류코드") or "").strip(),
                ksic_name=ksic_n.strip(),
                sido_name=(row.get("시도명") or "").strip(),
                sigungu_name=(row.get("시군구명") or "").strip(),
                admin_dong_name=(row.get("행정동명") or "").strip(),
                legal_dong_name=(row.get("법정동명") or "").strip(),
                parcel_address=(row.get("지번주소") or "").strip(),
                road_address=(row.get("도로명주소") or "").strip(),
                postal_code=postal,
                district=_district(
                    row.get("시군구명") or "",
                    row.get("행정동명") or "",
                    row.get("법정동명") or "",
                ),
                longitude=lng,
                latitude=lat,
            )
            pending.append(sg)
            if len(pending) >= _CHUNK:
                db.add_all(pending)
                db.commit()
                inserted += len(pending)
                pending.clear()

    if pending:
        db.add_all(pending)
        db.commit()
        inserted += len(pending)

    logger.info("[gourmet sgma] CSV 적재 완료 — %s건 (%s)", inserted, csv_path)
    return inserted, deleted


def sgma_restaurant_detail_dict(r: SgmaRestaurant) -> dict:
    """``RestaurantDetailResponse`` 와 동일 키를 갖는 dict — 공공 행용."""
    slug, label = classify_sgma_category(r.biz_mid_name, r.biz_minor_name, r.ksic_name)
    nm = _display_name(r.store_name, r.branch_name)
    addr_line = r.road_address or r.parcel_address or ""
    desc_parts = [
        p
        for p in (
            r.biz_minor_name.strip() or None,
            r.ksic_name.strip() or None,
            f"사업자번호(상가업소번호) {r.biz_number}",
        )
        if p
    ]
    desc = " · ".join(desc_parts)
    image_url = image_url_for_restaurant(nm, slug, desc)
    address_parts = [
        p
        for p in (
            addr_line,
            r.postal_code and f"(우편번호 {r.postal_code})" or "",
        )
        if p
    ]
    addr_block = "\n".join(address_parts).strip()

    return {
        "id": r.id,
        "name": nm,
        "category_slug": slug,
        "category_label": label,
        "district": r.district or r.sigungu_name or "",
        "description": desc,
        "image_url": image_url,
        "view_count": 0,
        "closed_weekdays": [],
        "closed_weekdays_label": "연중무휴 (휴무 정보 없음)",
        "address": addr_block,
        "opening_hours": "공공데이터에 영업 시간이 없습니다.",
        "phone": None,
        "instagram_url": None,
        "reservation_available": False,
        "reservation_note": "",
        "menu_items": [],
    }


def maybe_import_sgma_on_startup(db: Session) -> None:
    raw = os.getenv("SGMA_RESTAURANT_CSV", "").strip()
    if not raw:
        return
    path = Path(raw).expanduser()
    try:
        ins, deleted = sync_sgma_restaurants_from_csv(db, path)
        logger.info(
            "[gourmet sgma] 시작 시 재적재 — 삭제 행수(대략)=%s 신규=%s 경로=%s",
            deleted,
            ins,
            path,
        )
    except FileNotFoundError:
        logger.warning("[gourmet sgma] SGMA_RESTAURANT_CSV 파일 없음: %s", path)
    except Exception:
        logger.exception("[gourmet sgma] CSV 재적재 실패 — path=%s", path)
        db.rollback()
