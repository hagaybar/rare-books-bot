"""Pydantic models for auth requests and responses."""
from pydantic import BaseModel, Field


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


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: str = Field(..., pattern="^(admin|full|limited|guest)$")
    token_limit: int = 50000


class UpdateUserRequest(BaseModel):
    role: str | None = Field(None, pattern="^(admin|full|limited|guest)$")
    is_active: bool | None = None
    token_limit: int | None = None
    new_password: str | None = Field(None, min_length=8)


class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    last_login: str | None
    tokens_used_this_month: int = 0
    token_limit: int = 50000
