import logging

from sqlalchemy.orm import Session

from apps.secom.app.models.user_model import SecUser
from apps.secom.app.repositories.user_repository import UserRepository
from apps.secom.app.schemas.user_schema import UserSchema

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session):
        self._repository = UserRepository(db)

    def save_user(self, user: UserSchema) -> SecUser:
        logger.info(
            "[secom.service] save_user 진입 — layer=service payload=%s",
            user.to_log_dict(),
        )
        saved = self._repository.save_user(user)
        logger.info(
            "[secom.service] save_user 완료 — repository 반환 id=%s role=%s",
            saved.id,
            saved.role.value,
        )
        return saved
