import logging

from fastapi import APIRouter
from sqlalchemy.orm import Session

from apps.secom.app.schemas.user_schema import UserSchema
from apps.secom.app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/secom", tags=["secom"])


class UserController:
    def save_user(self, user: UserSchema, db: Session):
        logger.info(
            "[secom.controller] save_user 진입 — layer=controller payload=%s",
            user.to_log_dict(),
        )
        service = UserService(db)
        saved = service.save_user(user)
        logger.info(
            "[secom.controller] save_user 완료 — service 반환 id=%s username=%s role=%s",
            saved.id,
            saved.username,
            saved.role.value,
        )
        return saved
