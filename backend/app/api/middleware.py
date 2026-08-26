import asyncio
from collections import deque
from math import ceil
from time import monotonic
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _RequestBodyTooLargeError(Exception):
    pass


class CalculationRequestGuardMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        rate_limit_requests: int,
        rate_limit_window_seconds: int,
        max_concurrent_requests: int,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window_seconds = rate_limit_window_seconds
        self.max_concurrent_requests = max_concurrent_requests
        self._accepted_at: deque[float] = deque()
        self._active_requests = 0
        self._state_lock = asyncio.Lock()

    @staticmethod
    def _error_response(
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any],
        *,
        retry_after: int | None = None,
    ) -> JSONResponse:
        headers = (
            {"Retry-After": str(retry_after)}
            if retry_after is not None
            else None
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": details,
                }
            },
            headers=headers,
        )

    @staticmethod
    def _is_calculation_request(scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"] == "/api/industry/calculate"
        )

    def _content_length(self, scope: Scope) -> int | None:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    async def _reserve_capacity(self) -> tuple[str | None, int | None]:
        now = monotonic()
        cutoff = now - self.rate_limit_window_seconds

        async with self._state_lock:
            while self._accepted_at and self._accepted_at[0] <= cutoff:
                self._accepted_at.popleft()

            if len(self._accepted_at) >= self.rate_limit_requests:
                retry_after = max(
                    1,
                    ceil(
                        self.rate_limit_window_seconds
                        - (now - self._accepted_at[0])
                    ),
                )
                return "rate", retry_after

            if self._active_requests >= self.max_concurrent_requests:
                return "capacity", 1

            self._accepted_at.append(now)
            self._active_requests += 1
            return None, None

    async def _release_capacity(self) -> None:
        async with self._state_lock:
            self._active_requests -= 1

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if not self._is_calculation_request(scope):
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            response = self._error_response(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "request_too_large",
                "Calculation request body is too large",
                {"maximum_bytes": self.max_body_bytes},
            )
            await response(scope, receive, send)
            return

        rejection, retry_after = await self._reserve_capacity()
        if rejection is not None:
            code = (
                "calculation_rate_limited"
                if rejection == "rate"
                else "calculation_capacity_exceeded"
            )
            message = (
                "Too many calculation requests"
                if rejection == "rate"
                else "Calculation capacity is currently full"
            )
            response = self._error_response(
                status.HTTP_429_TOO_MANY_REQUESTS,
                code,
                message,
                {"retry_after_seconds": retry_after},
                retry_after=retry_after,
            )
            await response(scope, receive, send)
            return

        received_bytes = 0

        async def receive_with_limit() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise _RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, receive_with_limit, send)
        except _RequestBodyTooLargeError:
            response = self._error_response(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "request_too_large",
                "Calculation request body is too large",
                {"maximum_bytes": self.max_body_bytes},
            )
            await response(scope, receive, send)
        finally:
            await self._release_capacity()
