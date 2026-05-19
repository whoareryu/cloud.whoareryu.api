"""FastAPI Dependency Injection — DB 세션·레포지토리."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from apps.database import get_db, get_sync_db
from apps.secom.app.repositories.user_repository import UserRepository
from apps.secom.app.services.user_service import UserService

# DB 세션
SyncSessionDep = Annotated[Session, Depends(get_sync_db)]
AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_user_repository(db: SyncSessionDep) -> UserRepository:
    return UserRepository(db)


def get_user_service(db: SyncSessionDep) -> UserService:
    return UserService(db)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
