from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    avatar: str | None = None
    role: Literal["admin", "user"]


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    role: Literal["admin", "user"]
    captcha_id: str = Field(min_length=20, max_length=100)
    captcha_code: str = Field(min_length=5, max_length=5)


class RegisterRequest(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=255)


class PasswordUpdateRequest(StrictModel):
    password: str = Field(min_length=1, max_length=1024)
    newPassword: str = Field(min_length=8, max_length=128)


class AccountCreate(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    avatar: str | None = Field(default=None, max_length=500)
    role: Literal["admin", "user"]


class AccountUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    avatar: str | None = Field(default=None, max_length=500)
