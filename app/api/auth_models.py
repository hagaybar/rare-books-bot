"""Pydantic models for auth requests and responses."""
import re

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    message: str = "Login successful"
    username: str
    role: str


class UserInfo(BaseModel):
    user_id: int
    username: str
    role: str
    is_active: bool = True
    token_limit: int | None = None
    tokens_used_this_month: int | None = None


def _validate_password_complexity(v: str) -> str:
    """Enforce password complexity: >= 8 chars, upper, lower, digit."""
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", v):
        raise ValueError("Password must contain at least one digit")
    return v


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: str = Field(..., pattern="^(admin|full|limited|guest)$")
    token_limit: int = 50000

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UpdateUserRequest(BaseModel):
    role: str | None = Field(None, pattern="^(admin|full|limited|guest)$")
    is_active: bool | None = None
    token_limit: int | None = None
    new_password: str | None = Field(None, min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_password_complexity(v)
        return v


class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    last_login: str | None
    tokens_used_this_month: int = 0
    token_limit: int = 50000
