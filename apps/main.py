from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from apps.adapters.db_health_adapter import SqlAlchemyDbHealthAdapter
from apps.database import get_db
from apps.doro.app.doro_director import DoroDirector
from apps.titanic.app.james_controller import JamesController

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whoareryu Main Page")


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



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)




