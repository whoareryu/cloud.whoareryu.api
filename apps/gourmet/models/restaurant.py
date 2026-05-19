from typing import TYPE_CHECKING

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.database import Base

if TYPE_CHECKING:
    from apps.gourmet.models.restaurant_view_stat import RestaurantViewStat


class Restaurant(Base):
    """서울 맛집 마스터 — 영업 요일·유사명 그룹 포함."""

    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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

    view_stat: Mapped["RestaurantViewStat | None"] = relationship(
        "RestaurantViewStat",
        back_populates="restaurant",
        uselist=False,
    )
