"""소상공인 상가 정보(공공데이터 CSV) 적재 테이블.

DB 테이블명은 요청에 따라 단수 ``restaurant`` 로 둠 (seed ``restaurants`` 와 분리).

"""

from __future__ import annotations

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.database import Base, IntIdPrimaryKeyMixin


class SgmaRestaurant(IntIdPrimaryKeyMixin, Base):
    """서울 음식 상가 업소 — 원본 코드·주소·좌표 보존."""

    __tablename__ = "restaurant"

    biz_number: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    store_name: Mapped[str] = mapped_column(Text, index=True)
    branch_name: Mapped[str] = mapped_column(Text, default="", server_default="")

    biz_major_code: Mapped[str] = mapped_column(String(8), default="", server_default="")
    biz_major_name: Mapped[str] = mapped_column(String(32), default="", server_default="")
    biz_mid_code: Mapped[str] = mapped_column(String(16), default="", server_default="")
    biz_mid_name: Mapped[str] = mapped_column(String(64), default="", server_default="")
    biz_minor_code: Mapped[str] = mapped_column(String(16), default="", server_default="")
    biz_minor_name: Mapped[str] = mapped_column(String(128), default="", server_default="")

    ksic_code: Mapped[str] = mapped_column(String(16), default="", server_default="")
    ksic_name: Mapped[str] = mapped_column(String(256), default="", server_default="")

    sido_name: Mapped[str] = mapped_column(String(32), default="", server_default="")
    sigungu_name: Mapped[str] = mapped_column(String(32), index=True, default="", server_default="")
    admin_dong_name: Mapped[str] = mapped_column(String(32), default="", server_default="")
    legal_dong_name: Mapped[str] = mapped_column(String(32), default="", server_default="")

    parcel_address: Mapped[str] = mapped_column(Text, default="", server_default="")
    road_address: Mapped[str] = mapped_column(Text, default="", server_default="")
    postal_code: Mapped[str] = mapped_column(String(16), default="", server_default="")

    district: Mapped[str] = mapped_column(
        String(128), default="", server_default="", index=True
    )
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
