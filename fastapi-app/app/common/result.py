from __future__ import annotations

from typing import Any, List

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field


class Result(BaseModel):
    code: str
    msg: str
    data: Any = None

    @staticmethod
    def success(data: Any = None):
        json_data = None
        if data is not None:
            json_data = jsonable_encoder(data)
        return Result(code="200", msg="请求成功", data=json_data)

class PageInfo(BaseModel):
    total: int = 0
    list: List[Any] = Field(default_factory=list)
