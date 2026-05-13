import logging
from typing import Any, Dict, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DbHealthCheckPort(Protocol):
    """DB 연결 확인용 포트. 구현체는 예외 대신 dict로 성공/실패를 돌려준다."""

    async def check_sql_time(self) -> Dict[str, Any]:
        ...


class SqlAlchemyDbHealthAdapter:
    """SQLAlchemy `AsyncSession`을 `DbHealthCheckPort`에 맞게 감싼다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_sql_time(self) -> Dict[str, Any]:
        try:
            result = await self._session.execute(text("SELECT NOW();"))
            now = result.scalar()
            return {
                "status": "success",
                "neon_time": str(now) if now is not None else None,
            }
        except Exception as e:
            logger.exception("DB 확인 쿼리 실패: %s", e)
            return {"status": "error", "message": str(e)}
