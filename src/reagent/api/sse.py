import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Poll interval (seconds) for disconnect detection between keepalive pings.
_POLL_INTERVAL = 1
_KEEPALIVE_TICKS = 15  # pings once every _POLL_INTERVAL x _KEEPALIVE_TICKS seconds


async def _event_stream(request: Request) -> AsyncGenerator[str]:
    """Async generator that yields SSE keepalive pings until disconnect."""
    # Emit first ping immediately so clients know the connection is live.
    yield _make_ping()
    ticks = 0
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        if await request.is_disconnected():
            return
        ticks += 1
        if ticks >= _KEEPALIVE_TICKS:
            ticks = 0
            yield _make_ping()


def _make_ping() -> str:
    """Build a single SSE ping frame."""
    payload = json.dumps({"type": "ping", "ts": datetime.now(UTC).isoformat()})
    return f"data: {payload}\n\n"


async def sse_endpoint(request: Request) -> StreamingResponse:
    """GET /api/events — Server-Sent Events stream.

    Emits one ``ping`` event immediately, then a keepalive every 15 seconds.
    The stream exits cleanly when the client disconnects.
    """
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
