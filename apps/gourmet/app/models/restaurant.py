from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.database import Base, IntIdPrimaryKeyMixin

if TYPE_CHECKING:
    from apps.gourmet.app.models.restaurant_view_stat import RestaurantViewStat


class Restaurant(IntIdPrimaryKeyMixin, Base):
    """서울 맛집 마스터 — 영업 요일·유사명 그룹 포함."""

    __tablename__ = "restaurants"

    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name_key: Mapped[str] = mapped_column(String(128), index=True)
    category_slug: Mapped[str] = mapped_column(String(32), index=True)
    category_label: Mapped[str] = mapped_column(String(32))
    district: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(String(512))
    # 월=0 … 일=6 (datetime.date.weekday)
    closed_weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}"
    )
    address: Mapped[str] = mapped_column(String(256), default="", server_default="")
    opening_hours: Mapped[str] = mapped_column(String(256), default="", server_default="")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reservation_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    reservation_note: Mapped[str] = mapped_column(String(256), default="", server_default="")
    menu_items: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    view_stat: Mapped["RestaurantViewStat | None"] = relationship(
        "RestaurantViewStat",
        back_populates="restaurant",
        uselist=False,
    )
