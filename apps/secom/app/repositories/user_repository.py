import logging

from sqlalchemy.orm import Session

from apps.auth.password import hash_password
from apps.secom.app.models.user_model import SecUser
from apps.secom.app.models.user_role import UserRole
from apps.secom.app.schemas.user_schema import UserSchema

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, db: Session):
        self._db = db

    def save_user(self, user: UserSchema) -> SecUser:
        payload = user.to_log_dict()
        logger.info(
            "[secom.repository] save_user 진입 — layer=repository payload=%s",
            payload,
        )

        role = UserRole(user.role.strip().lower())
        entity = SecUser(
            username=user.username.strip(),
            email=user.email.strip().lower(),
            nickname=user.nickname.strip(),
            password_hash=hash_password(user.password),
            role=role,
        )
        self._db.add(entity)
        self._db.commit()
        self._db.refresh(entity)

        logger.info(
            "[secom.repository] save_user 완료 — id=%s username=%s email=%s "
            "nickname=%s role=%s (password_hash 저장됨, 평문 미저장)",
            entity.id,
            entity.username,
            entity.email,
            entity.nickname,
            entity.role.value,
        )
        return entity
