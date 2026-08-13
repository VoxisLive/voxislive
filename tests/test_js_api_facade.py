"""Pins the JsApi/OverlayJsApi facades (webui.py) that enforce the actual
JS-exposure boundary. See _JsApiFacade's docstring: pywebview's own leading-
underscore convention is cosmetic (it only shapes the auto-generated
window.pywebview.api stub) — the native message-bridge dispatcher resolves
any attribute name via a raw getattr() with no allowlist, so passing the full
Bridge instance as js_api= would let JS invoke every "private" method on it.
These tests make sure the facades (a) never carry an underscore-prefixed name,
(b) only list names that exist on Bridge, and (c) stay in sync with what the
shipped JS actually calls, so a new app().X(...) call added without updating
the allowlist fails loudly here instead of silently doing nothing in the app.
"""
import re
from pathlib import Path

from app.webui import _OVERLAY_HTML, Bridge, JsApi, OverlayJsApi

WEB_DIR = Path(__file__).parents[1] / "app" / "web"
APP_JS = (WEB_DIR / "app.js").read_text(encoding="utf-8")


def _js_api_calls(src: str) -> set:
    return set(re.findall(r"\bapi\(\)\.([A-Za-z_][A-Za-z0-9_]*)", src))


def _pywebview_api_calls(src: str) -> set:
    return set(re.findall(r"window\.pywebview\.api\.([A-Za-z_][A-Za-z0-9_]*)", src))


def test_no_exposed_name_is_underscore_prefixed():
    for name in JsApi._EXPOSED:
        assert not name.startswith("_"), name
    for name in OverlayJsApi._EXPOSED:
        assert not name.startswith("_"), name


def test_exposed_names_exist_and_are_callable_on_bridge():
    for name in (*JsApi._EXPOSED, *OverlayJsApi._EXPOSED):
        assert hasattr(Bridge, name), f"{name} is not a Bridge method"
        assert callable(getattr(Bridge, name))


def test_no_duplicate_entries():
    assert len(JsApi._EXPOSED) == len(set(JsApi._EXPOSED))
    assert len(OverlayJsApi._EXPOSED) == len(set(OverlayJsApi._EXPOSED))


def test_facade_only_carries_allowlisted_attributes():
    # Construct from a stub target exposing every name (public AND
    # underscore) via __getattr__, and confirm the facade only ever binds
    # the allowlisted ones — the underscore one must never leak through.
    class _Stub:
        def _private_should_never_leak(self):
            return "leaked"

        def __getattr__(self, name):
            return lambda *a, **k: name

    stub = _Stub()
    facade = JsApi(stub)
    assert not hasattr(facade, "_private_should_never_leak")
    assert not any(n.startswith("_") for n in vars(facade))
    for name in JsApi._EXPOSED:
        assert getattr(facade, name)() == name


def test_main_window_facade_covers_every_shipped_js_call():
    called = _js_api_calls(APP_JS)
    missing = called - set(JsApi._EXPOSED)
    assert not missing, (
        f"app.js calls api().{sorted(missing)} but JsApi._EXPOSED does not "
        "list it — the call would silently do nothing at runtime. Add it to "
        "JsApi._EXPOSED in webui.py."
    )


def test_overlay_facade_covers_every_overlay_html_call():
    called = _pywebview_api_calls(_OVERLAY_HTML)
    missing = called - set(OverlayJsApi._EXPOSED)
    assert not missing, (
        f"_OVERLAY_HTML calls window.pywebview.api.{sorted(missing)} but "
        "OverlayJsApi._EXPOSED does not list it."
    )
