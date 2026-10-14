from __future__ import annotations

import logging
import secrets
import time

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def setup_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_request(request: Request, call_next):
        correlation_id = secrets.token_hex(12)
        request.state.request_id = correlation_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "request_aborted request_id=%s method=%s status=500 duration_ms=%.2f exception_type=%s",
                correlation_id,
                request.method,
                elapsed_ms,
                type(exc).__name__,
            )
            raise

        route = request.scope.get("route")
        route_template = getattr(route, "path", "<unmatched>")
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = correlation_id
        logger.info(
            "request_complete request_id=%s method=%s route=%s status=%s duration_ms=%.2f",
            correlation_id,
            request.method,
            route_template,
            response.status_code,
            elapsed_ms,
        )
        return response
