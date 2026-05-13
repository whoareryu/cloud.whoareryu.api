import logging
import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

load_dotenv()

logger = logging.getLogger(__name__)

# Neon DB URL 가져오기
DATABASE_URL = os.getenv("DATABASE_URL")

# 초기화 실패 시 메시지 (에러 표기용)
DATABASE_INIT_ERROR: Optional[str] = None

engine = None
AsyncSessionLocal = None

if not DATABASE_URL:
    DATABASE_INIT_ERROR = "에러: DATABASE_URL이 환경 변수에 설정되지 않았습니다."
    logger.error(DATABASE_INIT_ERROR)
else:
    try:
        engine = create_async_engine(DATABASE_URL, echo=True)
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    except Exception as e:
        DATABASE_INIT_ERROR = f"에러: DB 엔진 생성 중 오류가 발생했습니다. ({type(e).__name__}: {e})"
        logger.exception(DATABASE_INIT_ERROR)

Base = declarative_base()


async def get_db():
    if DATABASE_INIT_ERROR or engine is None or AsyncSessionLocal is None:
        raise RuntimeError(
            DATABASE_INIT_ERROR or "에러: 데이터베이스를 초기화할 수 없습니다."
        )
    async with AsyncSessionLocal() as session:
        yield session
