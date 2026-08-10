"""Qwen realtime WebSocket must keep its explicit ping keepalive/timeout.

`_connect` pins `ping_interval=20` (app/qwen_translator.py `PING_TIMEOUT`)
and a `ping_timeout` generous enough that a busy-but-healthy DashScope
session under heavy load isn't closed out from under it by a missed PONG --
DashScope confirmed (support ticket, 2026-08-10) that a large in-flight
session can leave its event loop too busy to answer a PONG promptly, and
recommended 600s or longer. Our own STALL_ROTATE_SECONDS/NO_OUTPUT_ROTATE_SECONDS
watchdogs (base_translator.py, 20s/22s) still catch a genuinely dead socket
in continuous-streaming mode, since they key off actual audio/event traffic
rather than the ping/pong handshake. This pins the kwarg on both the modern
(`additional_headers`) and legacy (`extra_headers`) connect paths so a future
refactor can't silently drop it.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.config import ENGINE_QWEN
from app.engines import make_translator


def _make():
    return make_translator(
        {}, "cs", engine=ENGINE_QWEN, key="dummy-key", model="test-model",
        on_audio=lambda *_: None, on_text=lambda *_: None,
        on_status=lambda *_: None, name="t")


def test_connect_sets_ping_keepalive_on_modern_api():
    tr = _make()
    fake_conn = object()
    with patch("websockets.connect", new=AsyncMock(return_value=fake_conn)) as mocked:
        result = asyncio.run(tr._connect())

    assert result is fake_conn
    mocked.assert_awaited_once()
    _, kwargs = mocked.call_args
    assert kwargs["ping_interval"] == 20
    assert kwargs["ping_timeout"] == 600
    assert "additional_headers" in kwargs


def test_connect_sets_ping_keepalive_on_legacy_fallback():
    # Older websockets releases reject `additional_headers`; _connect must
    # retry with `extra_headers` and still carry the same keepalive settings.
    tr = _make()
    fake_conn = object()
    calls = []

    async def connect_side_effect(*args, **kwargs):
        calls.append(kwargs)
        if "additional_headers" in kwargs:
            raise TypeError("additional_headers unsupported")
        return fake_conn

    with patch("websockets.connect", side_effect=connect_side_effect):
        result = asyncio.run(tr._connect())

    assert result is fake_conn
    assert len(calls) == 2
    assert "extra_headers" in calls[1]
    for kwargs in calls:
        assert kwargs["ping_interval"] == 20
        assert kwargs["ping_timeout"] == 600
