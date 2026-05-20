import asyncio
import sys
from pathlib import Path

# Windows: psycopg async는 ProactorEventLoop와 호환되지 않음
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# `cd backend/apps` 후 `uvicorn main:app` 실행 시, cwd만 path에 들어가 `apps` 패키지를 못 찾음 → backend 루트 추가
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.auth.auth_router import LoginRequest, SignupRequest, UserPublic, router as auth_router
from apps.auth.auth_router import _db_unavailable as auth_db_unavailable
from apps.auth.auth_router import login as auth_login
from apps.auth.auth_router import signup as auth_signup
from apps.auth.user_model import User  # noqa: F401 — Base.metadata 등록
from apps.secom.app.controllers.user_controller import router as secom_router
from apps.gourmet.router import router as gourmet_router
from apps.gourmet.services.restaurant_profile_service import sync_restaurant_profiles
from apps.gourmet.services.today_picks_service import ensure_restaurants_seeded
from apps.database import SyncSessionLocal
from apps.matrix.app.keymaker import MissingGeminiKeyError, keymaker
from apps.adapters.db_health_adapter import SqlAlchemyDbHealthAdapter
from urllib.parse import urlparse

from apps.database import DATABASE_URL, ensure_sync_tables, get_db, get_sync_db, init_db
from apps.doro.app.doro_director import DoroDirector
from apps.titanic.app.james_controller import JamesController

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        host = urlparse(DATABASE_URL or "").hostname or "(unknown)"
        await init_db()
        ensure_sync_tables()
        if SyncSessionLocal is not None:
            db = SyncSessionLocal()
            try:
                ensure_restaurants_seeded(db)
                sync_restaurant_profiles(db)
            finally:
                db.close()
        logger.info(
            "Neon PostgreSQL 연결 완료 (host=%s). "
            "콘솔 Tables 가 비어 있으면 backend/.env 의 DATABASE_URL 이 "
            "Neon 대시보드 Connection string 과 같은지 확인하세요.",
            host,
        )
    except RuntimeError as e:
        logger.warning("DB 초기화 스킵: %s", e)
    yield


app = FastAPI(title="Whoareryu Main Page", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(secom_router)
app.include_router(gourmet_router)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=32000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None


def _gemini_error_detail(exc: Exception) -> tuple[int, str]:
    """Gemini API 오류를 HTTP 상태·사용자 메시지로 변환."""
    msg = str(exc)
    upper = msg.upper()
    if "API_KEY_INVALID" in upper or "API KEY NOT FOUND" in upper:
        return (
            503,
            "GEMINI_API_KEY가 유효하지 않습니다. backend/.env 에 Google AI Studio에서 발급한 키를 넣고 서버를 재시작하세요.",
        )
    if "PERMISSION_DENIED" in upper or "403" in msg:
        return 503, "Gemini API 권한이 없습니다. API 키와 프로젝트 설정을 확인하세요."
    if "QUOTA" in upper or "RESOURCE_EXHAUSTED" in upper:
        return 503, "Gemini API 할당량이 초과되었습니다. 잠시 후 다시 시도하세요."
    return 502, msg


def _messages_to_gemini_contents(messages: list[ChatMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = "model" if m.role == "assistant" else "user"
        text = m.content.strip()
        if not text:
            raise HTTPException(status_code=422, detail="빈 content는 허용되지 않습니다.")
        out.append({"role": role, "parts": [text]})
    return out


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("요청 검증 오류: %s", exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "message": "요청 검증 오류",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "message": exc.detail},
        )
    logger.exception("처리되지 않은 오류 (%s): %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": str(exc),
            "type": type(exc).__name__,
        },
    )


async def get_db_health_adapter(
    db: AsyncSession = Depends(get_db),
) -> SqlAlchemyDbHealthAdapter:
    return SqlAlchemyDbHealthAdapter(db)


@app.get("/")
def read_root():
    return {"message": "FastAPI 메인 페이지.", "docs": "/docs"}


@app.post("/chat")
def chat(body: ChatRequest):
    """JSON 메시지 목록으로 Gemini에 질의하고, 응답 텍스트를 반환합니다."""
    if body.messages[-1].role != "user":
        raise HTTPException(
            status_code=422,
            detail="messages의 마지막 요소는 role=user 여야 합니다.",
        )
    try:
        gemini = keymaker.generative_model(body.model)
        model_used = keymaker.resolve_model_name(body.model or keymaker.gemini_model_name)
    except MissingGeminiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    contents = _messages_to_gemini_contents(body.messages)
    try:
        response = gemini.generate_content(contents)
    except Exception as e:
        logger.exception("Gemini generate_content 실패")
        status, detail = _gemini_error_detail(e)
        raise HTTPException(status_code=status, detail=detail) from e

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise HTTPException(
            status_code=502,
            detail="모델이 텍스트 응답을 반환하지 않았습니다.",
        )
    return {"text": text, "model": model_used}


@app.get("/db-check")
async def check_db(
    db_health: SqlAlchemyDbHealthAdapter = Depends(get_db_health_adapter),
):
    """Neon 등 DB 연결 확인. SQL 실패 시에도 HTTP 200 + status=error 본문."""
    return await db_health.check_sql_time()


@app.get("/titanic/data")
def read_titanic_data():
    james = JamesController()
    df = james.get_data()

    return df.to_dict(orient="records")

@app.get("/titanic/count")
def read_titanic_count():
    james = JamesController()
    count = james.get_count()
    return {"count": count}

@app.get("/titanic/count_survived")
def read_titanic_count_survived():
    james = JamesController() 
    count_survived = james.get_count_survived()
    return {"count_survived": count_survived}

@app.get("/titanic/count_dead")
def read_titanic_count_dead():
    james = JamesController()
    count_dead = james.get_count_dead()
    return {"count_dead": count_dead}

@app.get("/titanic/tree")
def read_titanic_tree():
    james = JamesController ()
    tree = james.has_decision_tree_model()
    return {"tree": tree}

@app.get("/titanic/model_name")
def read_titanic_model():
    james = JamesController()
    model = james.get_training_model_name()
    return {"model": model}


@app.get("/doro/data")
def read_doro_data():
    doro = DoroDirector()
    df = doro.get_data()

    return df.to_dict(orient="records")

#회원가입
@app.post("/signup", response_model=UserPublic, status_code=201, tags=["회원가입"])
def signup_member(body: SignupRequest, db: Session = Depends(get_sync_db)):
    """회원가입 — localhost:3000 → Neon `users` 단일 테이블."""
    auth_db_unavailable()
    logger.info(
        "[main] 회원가입 요청 — username=%s email=%s nickname=%s",
        body.username,
        body.email,
        body.nickname,
    )
    return auth_signup(body, db)


@app.post("/login", response_model=UserPublic, tags=["로그인"])
def login_member(body: LoginRequest, db: Session = Depends(get_sync_db)):
    """로그인 — users 테이블 검증 + last_login_at 갱신."""
    auth_db_unavailable()
    logger.info("[main] 로그인 요청 — username=%s", body.username)
    return auth_login(body, db)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)




