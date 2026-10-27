import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_username(value: str) -> str:
    if not isinstance(value, str):
        return value
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        not normalized
        or len(normalized) > 255
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise ValueError("账号格式无效")
    return normalized


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    avatar: str | None = None
    role: Literal["admin", "user"]
    is_experience: bool = False


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    role: Literal["admin", "user"]
    captcha_id: str = Field(min_length=20, max_length=100)
    captcha_code: str = Field(min_length=5, max_length=5)

    @field_validator("username", mode="before")
    @classmethod
    def normalized_username(cls, value):
        return normalize_username(value)


class RegisterRequest(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=255)

    @field_validator("username", mode="before")
    @classmethod
    def normalized_username(cls, value):
        return normalize_username(value)


class PasswordUpdateRequest(StrictModel):
    password: str = Field(min_length=1, max_length=1024)
    newPassword: str = Field(min_length=8, max_length=128)


class AccountCreate(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    avatar: str | None = Field(default=None, max_length=500)
    role: Literal["admin", "user"]

    @field_validator("username", mode="before")
    @classmethod
    def normalized_username(cls, value):
        return normalize_username(value)


class AccountUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    avatar: str | None = Field(default=None, max_length=500)
