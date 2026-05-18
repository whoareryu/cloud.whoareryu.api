import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.auth.password import hash_password, verify_password
from apps.auth.user_model import User
from apps.database import DATABASE_INIT_ERROR, get_sync_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class UsernameCheckResponse(BaseModel):
    username: str
    available: bool
    message: str


class NicknameCheckResponse(BaseModel):
    nickname: str
    available: bool
    message: str


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    password_confirm: str = Field(..., min_length=6, max_length=128)
    email: EmailStr
    nickname: str = Field(..., min_length=1, max_length=64)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "아이디는 영문, 숫자, 밑줄(_)만 사용 가능하며 3~32자여야 합니다."
            )
        return v

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("비밀번호가 일치하지 않습니다.")
        return self


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class UserPublic(BaseModel):
    username: str
    nickname: str
    email: str


def _db_unavailable() -> None:
    if DATABASE_INIT_ERROR:
        raise HTTPException(
            status_code=503,
            detail="데이터베이스에 연결할 수 없습니다. DATABASE_URL을 확인해 주세요.",
        )


def _username_taken(db: Session, username: str) -> bool:
    normalized = username.strip().lower()
    return (
        db.execute(
            select(User.id).where(func.lower(User.username) == normalized).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _nickname_taken(db: Session, nickname: str) -> bool:
    normalized = nickname.strip().lower()
    return (
        db.execute(
            select(User.id).where(func.lower(User.nickname) == normalized).limit(1)
        ).scalar_one_or_none()
        is not None
    )


@router.get("/check-username", response_model=UsernameCheckResponse)
def check_username(
    username: str = Query(..., min_length=3, max_length=32),
    db: Session = Depends(get_sync_db),
):
    _db_unavailable()
    name = username.strip()
    if not _USERNAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="아이디는 영문, 숫자, 밑줄(_)만 사용 가능하며 3~32자여야 합니다.",
        )
    try:
        taken = _username_taken(db, name)
    except Exception:
        logger.exception("아이디 중복 확인 실패")
        raise HTTPException(
            status_code=503, detail="아이디 중복 확인 중 오류가 발생했습니다."
        ) from None

    if taken:
        return UsernameCheckResponse(
            username=name,
            available=False,
            message="이미 사용 중인 아이디입니다. 다른 아이디를 사용해 주세요.",
        )
    return UsernameCheckResponse(
        username=name,
        available=True,
        message="사용 가능한 아이디입니다.",
    )


@router.get("/check-nickname", response_model=NicknameCheckResponse)
def check_nickname(
    nickname: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_sync_db),
):
    _db_unavailable()
    nick = nickname.strip()
    if not nick:
        raise HTTPException(status_code=400, detail="닉네임을 입력해 주세요.")

    try:
        taken = _nickname_taken(db, nick)
    except Exception:
        logger.exception("닉네임 중복 확인 실패")
        raise HTTPException(
            status_code=503, detail="닉네임 중복 확인 중 오류가 발생했습니다."
        ) from None

    if taken:
        return NicknameCheckResponse(
            nickname=nick,
            available=False,
            message="사용중인 닉네임입니다.",
        )
    return NicknameCheckResponse(
        nickname=nick,
        available=True,
        message="사용 가능한 닉네임입니다.",
    )


@router.post("/signup", response_model=UserPublic, status_code=201)
def signup(body: SignupRequest, db: Session = Depends(get_sync_db)):
    _db_unavailable()
    if body.password != body.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    if _username_taken(db, body.username):
        raise HTTPException(
            status_code=409,
            detail="이미 사용 중인 아이디입니다. 다른 아이디를 사용해 주세요.",
        )

    if _nickname_taken(db, body.nickname):
        raise HTTPException(status_code=409, detail="사용중인 닉네임입니다.")

    if (
        db.execute(select(User).where(User.email == body.email.lower()).limit(1))
        .scalar_one_or_none()
    ):
        raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다.")

    user = User(
        username=body.username.strip(),
        email=body.email.lower(),
        nickname=body.nickname.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        logger.exception("회원가입 DB 저장 실패")
        raise HTTPException(status_code=500, detail="회원가입 처리 중 오류가 발생했습니다.") from None

    return UserPublic(username=user.username, nickname=user.nickname, email=user.email)


@router.post("/login", response_model=UserPublic)
def login(body: LoginRequest, db: Session = Depends(get_sync_db)):
    _db_unavailable()
    user = db.execute(
        select(User)
        .where(func.lower(User.username) == body.username.strip().lower())
        .limit(1)
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return UserPublic(username=user.username, nickname=user.nickname, email=user.email)
