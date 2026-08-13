"""QwenTranslator._connect() builds a wss:// URL by interpolating `workspace`
and `model` -- both come from the server (session-key issuance, or the
sibling-pool fallback), and were used unvalidated. Confirmed against the real
`websockets` library: a workspace of "attacker.example.com?x=" is ACCEPTED by
its URI parser and resolves the connection host to attacker.example.com:443,
carrying the real DashScope Authorization header (and the live audio stream)
there instead of Alibaba's endpoint. Requires the session-key response itself
to be attacker-influenced (backend compromise/bug), but a value that builds a
security-relevant URL should be validated regardless of who is nominally
trusted to send it. This pins the fix: an out-of-shape value falls back to the
known-good default instead of ever reaching websockets.connect().
"""
import asyncio
import sys
import types

import pytest

import app.qwen_translator as qwen
from app.config import QWEN_TRANSLATE_MODEL, QWEN_WORKSPACE


def _noop(*a, **k):
    pass


def _make(workspace=QWEN_WORKSPACE, model=QWEN_TRANSLATE_MODEL):
    return qwen.QwenTranslator(
        "k", "en", on_audio=_noop, on_text=_noop, on_status=_noop,
        workspace=workspace, model=model)


class _FakeConn:
    closed = False


def _patch_websockets_connect(monkeypatch):
    captured = {}

    async def fake_connect(url, **kwargs):
        captured["url"] = url
        return _FakeConn()

    fake_module = types.SimpleNamespace(connect=fake_connect)
    monkeypatch.setitem(sys.modules, "websockets", fake_module)
    return captured


@pytest.mark.parametrize("payload", [
    "attacker.example.com?x=",   # confirmed: websockets resolves host to this
    "attacker.example.com#",
    "x@attacker.example.com",
    "attacker.example.com/x",
    "",
    "a" * 65,
])
def test_malicious_workspace_falls_back_to_default_host(monkeypatch, payload):
    captured = _patch_websockets_connect(monkeypatch)
    tr = _make(workspace=payload)
    asyncio.run(tr._connect())
    assert captured["url"].startswith(f"wss://{QWEN_WORKSPACE}.")
    assert "attacker" not in captured["url"]


def test_malicious_model_falls_back_to_default(monkeypatch):
    captured = _patch_websockets_connect(monkeypatch)
    tr = _make(model="attacker.example.com?x=")
    asyncio.run(tr._connect())
    assert f"model={QWEN_TRANSLATE_MODEL}" in captured["url"]
    assert "attacker" not in captured["url"]


def test_legitimate_workspace_and_model_pass_through_unchanged(monkeypatch):
    captured = _patch_websockets_connect(monkeypatch)
    tr = _make(workspace="ws-abc123XYZ", model=QWEN_TRANSLATE_MODEL)
    asyncio.run(tr._connect())
    assert captured["url"] == (
        f"wss://ws-abc123XYZ.ap-southeast-1.maas.aliyuncs.com"
        f"/api-ws/v1/realtime?model={QWEN_TRANSLATE_MODEL}")
