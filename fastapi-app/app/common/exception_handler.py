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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"code": "422", "msg": "请求参数错误", "errors": jsonable_encoder([
                {key: value for key, value in error.items() if key not in {"input", "ctx"}}
                for error in exc.errors()
            ])}
        )



class SafeErrorMiddleware:
    """Contain HTTP failures before ServerErrorMiddleware can re-raise secrets."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            correlation_id = request_id(Request(scope))
            # Never format the exception, its cause/context, source lines or locals.
            logger.error(
                "unhandled_exception request_id=%s exception_type=%s\n%s",
                correlation_id, type(exc).__name__, _stack_locations(exc),
            )
            if not response_started:
                response = JSONResponse(
                    status_code=500,
                    content={"code": "500", "msg": "系统错误"},
                    headers={"X-Request-ID": correlation_id},
                )
                await response(scope, receive, send)
                return
        else:
            return

        # Streaming/background failures cannot replace an already-sent response.
        # Raise outside the except block: no original exception context reaches
        # Starlette/Uvicorn, while the server still terminates an incomplete stream.
        raise RuntimeError("HTTP response failed after headers were sent") from None
