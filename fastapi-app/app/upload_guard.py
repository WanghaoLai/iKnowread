from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable, Collection

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger(__name__)


class UploadConcurrencyMiddleware(BaseHTTPMiddleware):
    """Bound multipart parsing before Starlette creates temporary files.

    Account storage locks run after request parsing, so they cannot protect the
    shared /tmp tmpfs from several simultaneous large multipart bodies. This
    process-wide gate is intentionally placed around the whole upload request.
    The production deployment uses one worker; multi-worker deployments need a
    host-level or distributed equivalent before they are supported.
    """

    def __init__(
        self,
        app,
        *,
        limit: int,
        queue_wait_seconds: float,
        paths: Collection[str],
    ) -> None:
        super().__init__(app)
        self._slots = asyncio.BoundedSemaphore(max(1, limit))
        self._queue_wait_seconds = max(0.01, queue_wait_seconds)
        self._paths = frozenset(paths)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "POST" or request.url.path not in self._paths:
            return await call_next(request)

        try:
            await asyncio.wait_for(
                self._slots.acquire(), timeout=self._queue_wait_seconds
            )
        except TimeoutError:
            logger.warning("upload_concurrency_rejected path=%s", request.url.path)
            return JSONResponse(
                status_code=429,
                content={"code": "429", "msg": "上传任务较多，请稍后重试"},
                headers={
                    "Retry-After": str(max(1, math.ceil(self._queue_wait_seconds)))
                },
            )

        try:
            return await call_next(request)
        finally:
            self._slots.release()
