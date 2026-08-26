import asyncio
import json
from collections import deque

from fastapi.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from app.api.middleware import CalculationRequestGuardMiddleware


def _calculation_scope() -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/industry/calculate",
        "raw_path": b"/api/industry/calculate",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }


async def _invoke(
    app: CalculationRequestGuardMiddleware,
    messages: deque[Message] | None = None,
) -> list[Message]:
    request_messages = messages or deque(
        [{"type": "http.request", "body": b"", "more_body": False}]
    )
    sent: list[Message] = []

    async def receive() -> Message:
        return request_messages.popleft()

    async def send(message: Message) -> None:
        sent.append(message)

    await app(_calculation_scope(), receive, send)
    return sent


def test_streamed_calculation_body_limit_cannot_be_bypassed() -> None:
    async def scenario() -> list[Message]:
        async def consume_body(
            scope: Scope,
            receive: Receive,
            send: Send,
        ) -> None:
            while (await receive()).get("more_body", False):
                pass
            await JSONResponse({"ok": True})(scope, receive, send)

        guard = CalculationRequestGuardMiddleware(
            consume_body,
            max_body_bytes=1_024,
            rate_limit_requests=10,
            rate_limit_window_seconds=60,
            max_concurrent_requests=1,
        )
        return await _invoke(
            guard,
            deque(
                [
                    {
                        "type": "http.request",
                        "body": b"a" * 600,
                        "more_body": True,
                    },
                    {
                        "type": "http.request",
                        "body": b"b" * 425,
                        "more_body": False,
                    },
                ]
            ),
        )

    sent = asyncio.run(scenario())
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"]["code"] == "request_too_large"


def test_concurrent_calculation_limit_rejects_excess_work() -> None:
    async def scenario() -> list[Message]:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_calculation(
            scope: Scope,
            receive: Receive,
            send: Send,
        ) -> None:
            started.set()
            await release.wait()
            await JSONResponse({"ok": True})(scope, receive, send)

        guard = CalculationRequestGuardMiddleware(
            slow_calculation,
            max_body_bytes=1_024,
            rate_limit_requests=10,
            rate_limit_window_seconds=60,
            max_concurrent_requests=1,
        )
        first = asyncio.create_task(_invoke(guard))
        await started.wait()
        rejected = await _invoke(guard)
        release.set()
        await first
        return rejected

    sent = asyncio.run(scenario())
    assert sent[0]["status"] == 429
    headers = dict(sent[0]["headers"])
    assert headers[b"content-type"] == b"application/json"
    assert headers[b"retry-after"] == b"1"
    assert json.loads(sent[1]["body"])["error"]["code"] == (
        "calculation_capacity_exceeded"
    )
