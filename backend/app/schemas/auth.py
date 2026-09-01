from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    admin_code: Optional[str] = Field(
        default=None, description="Optional; grants admin role if it matches the server's admin code."
    )


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_admin: bool
    username: str


class UserPublic(BaseModel):
    id: str
    username: str
    email: EmailStr
    is_admin: bool

    class Config:
        from_attributes = True
