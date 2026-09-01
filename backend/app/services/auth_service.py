"""Business logic for registration/login (Service layer pattern)."""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


class AuthService:
    def __init__(self, db: Session):
        self.users = UserRepository(db)

    def register(self, payload: RegisterRequest) -> TokenResponse:
        if self.users.get_by_username(payload.username):
            raise UserAlreadyExistsError("Username is already taken")
        if self.users.get_by_email(payload.email):
            raise UserAlreadyExistsError("Email is already registered")

        is_admin = bool(payload.admin_code) and payload.admin_code == settings.ADMIN_REGISTRATION_CODE
        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            is_admin=is_admin,
        )
        self.users.add(user)
        return self._issue_token(user)

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.users.get_by_username(payload.username)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise InvalidCredentialsError("Invalid username or password")
        if not user.is_active:
            raise InvalidCredentialsError("Account is disabled")
        return self._issue_token(user)

    @staticmethod
    def _issue_token(user: User) -> TokenResponse:
        token = create_access_token(subject=user.id, extra_claims={"is_admin": user.is_admin})
        return TokenResponse(access_token=token, is_admin=user.is_admin, username=user.username)
