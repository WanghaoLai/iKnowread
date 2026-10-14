import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette import status
from starlette.responses import JSONResponse

from app.observability import request_id


logger = logging.getLogger(__name__)


def _stack_locations(exc: Exception) -> str:
    locations: list[str] = []
    current = exc.__traceback__
    while current is not None:
        code = current.tb_frame.f_code
        locations.append(f"{code.co_filename}:{current.tb_lineno} in {code.co_name}")
        current = current.tb_next
    return "\n".join(locations)


# 自定义异常类
class CustomException(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code


def setup_exceptions(app: FastAPI):
    @app.exception_handler(CustomException)
    async def custom_exception_handler(request: Request, exc: CustomException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": str(exc.status_code), "msg": exc.message},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": str(exc.status_code), "msg": str(exc.detail)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validate_exception_handler(request: Request, exc: RequestValidationError):
        """处理422异常"""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"code": "422", "msg": "请求参数错误", "errors": jsonable_encoder([
                {key: value for key, value in error.items() if key not in {"input", "ctx"}}
                for error in exc.errors()
            ])}
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # 记录调用栈和异常类型，不记录异常消息、请求正文、查询参数或请求头，
        # 避免上游 SDK/数据库异常意外把 API Key 或用户正文写入日志。
        stack = _stack_locations(exc)
        correlation_id = request_id(request)
        logger.error(
            "unhandled_exception request_id=%s exception_type=%s\n%s",
            correlation_id,
            type(exc).__name__,
            stack,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "500", "msg": "系统错误"},
            headers={"X-Request-ID": correlation_id},
        )
