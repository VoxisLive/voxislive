"""voxis_client: local JWT claim/expiry logic and the proactive refresh path
(all network + disk I/O mocked)."""
import base64
import json
import time

import pytest

import app.voxis_client as vc


def _make_jwt(exp=None, **claims):
    if exp is not None:
        claims["exp"] = exp
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps(claims).encode()).rstrip(b"=")
    return (header + b"." + payload + b".sig").decode()


def test_jwt_claims_roundtrip():
    tok = _make_jwt(exp=123, id="user1")
    claims = vc._jwt_claims(tok)
    assert claims["id"] == "user1" and claims["exp"] == 123
    assert vc._jwt_claims("garbage") is None


def test_is_expired_boundaries():
    assert vc._is_expired(_make_jwt(exp=time.time() - 10)) is True
    assert vc._is_expired(_make_jwt(exp=time.time() + 3600)) is False
    # Missing/garbled exp → treated as not-expired (server decides).
    assert vc._is_expired(_make_jwt(id="x")) is False
    assert vc._is_expired("garbage") is False


class _FakeResp:
    def __init__(self, status_code, body=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


@pytest.fixture
def refresh_env(monkeypatch):
    """Official build + no throttle + captured set_jwt + fake HTTP."""
    calls = {"posts": [], "stored": []}
    monkeypatch.setattr(vc, "IS_OFFICIAL_RELEASE", True)
    monkeypatch.setattr(vc, "_last_refresh_attempt", 0.0)
    monkeypatch.setattr(vc, "set_jwt", lambda tok: calls["stored"].append(tok))

    class _FakeHttp:
        def post(self, url, headers=None, timeout=None, **kw):
            calls["posts"].append((url, headers))
            return calls["resp"]

    monkeypatch.setattr(vc, "_http", _FakeHttp())
    return calls


def test_refresh_skipped_when_expiry_far(refresh_env):
    tok = _make_jwt(exp=time.time() + 30 * 24 * 3600)  # 30 days out
    assert vc._maybe_refresh_jwt(tok) == tok
    assert refresh_env["posts"] == []


def test_refresh_renews_near_expiry(refresh_env):
    old = _make_jwt(exp=time.time() + 3600, id="u")  # inside the 3-day margin
    new = _make_jwt(exp=time.time() + 14 * 24 * 3600, id="u")
    refresh_env["resp"] = _FakeResp(200, {"token": new})
    out = vc._maybe_refresh_jwt(old)
    assert out == new
    assert refresh_env["stored"] == [new]
    url, headers = refresh_env["posts"][0]
    assert url.endswith("/dashboard/api/collections/users/auth-refresh")
    # PocketBase expects the RAW token — no Bearer prefix.
    assert headers["Authorization"] == old


def test_refresh_failure_keeps_current_token(refresh_env):
    old = _make_jwt(exp=time.time() + 3600)
    refresh_env["resp"] = _FakeResp(401, {}, text="unauthorized")
    assert vc._maybe_refresh_jwt(old) == old
    assert refresh_env["stored"] == []


def test_refresh_throttled_after_attempt(refresh_env, monkeypatch):
    old = _make_jwt(exp=time.time() + 3600)
    refresh_env["resp"] = _FakeResp(500)
    vc._maybe_refresh_jwt(old)
    assert len(refresh_env["posts"]) == 1
    # Second call inside the throttle window must not hit the network again.
    vc._maybe_refresh_jwt(old)
    assert len(refresh_env["posts"]) == 1


def test_refresh_disabled_on_oss_build(refresh_env, monkeypatch):
    monkeypatch.setattr(vc, "IS_OFFICIAL_RELEASE", False)
    old = _make_jwt(exp=time.time() + 60)
    assert vc._maybe_refresh_jwt(old) == old
    assert refresh_env["posts"] == []


# --- Device headers on /auth/session-key (one-free-tier-per-device) ---


def test_device_headers_sanitized(monkeypatch):
    import app.device_id as device_id
    monkeypatch.setattr(
        device_id, "fingerprint",
        lambda: {"primary": " guid-1 ", "secondary": "board|üuid\x01"})
    h = vc._device_headers()
    # Whitespace stripped; non-ASCII and non-printable bytes dropped so the
    # header can never make the HTTP request itself fail.
    assert h["X-Voxis-Device-Primary"] == "guid-1"
    assert h["X-Voxis-Device-Secondary"] == "board|uid"


def test_device_headers_secondary_strong_flag(monkeypatch):
    import app.device_id as device_id
    monkeypatch.setattr(
        device_id, "fingerprint",
        lambda: {"primary": "guid-1", "secondary": "hw", "secondary_strong": True})
    h = vc._device_headers()
    assert h["X-Voxis-Device-Secondary-Strong"] == "1"


def test_device_headers_secondary_weak_omits_flag(monkeypatch):
    # Registry-fallback secondary (manufacturer|product, shared across every
    # unit of that model) must not claim strength — the server must not
    # merge/block accounts on it alone (see device_id.fingerprint docstring).
    import app.device_id as device_id
    monkeypatch.setattr(
        device_id, "fingerprint",
        lambda: {"primary": "guid-1", "secondary": "hw", "secondary_strong": False})
    h = vc._device_headers()
    assert "X-Voxis-Device-Secondary-Strong" not in h


def test_device_headers_omit_empty_components(monkeypatch):
    import app.device_id as device_id
    monkeypatch.setattr(
        device_id, "fingerprint", lambda: {"primary": "", "secondary": "hw"})
    h = vc._device_headers()
    assert "X-Voxis-Device-Primary" not in h
    assert h["X-Voxis-Device-Secondary"] == "hw"


def test_device_headers_fail_open(monkeypatch):
    import app.device_id as device_id

    def boom():
        raise RuntimeError("wmi unavailable")

    monkeypatch.setattr(device_id, "fingerprint", boom)
    assert vc._device_headers() == {}


def test_session_key_sends_device_headers(monkeypatch):
    monkeypatch.setattr(vc, "IS_OFFICIAL_RELEASE", True)
    monkeypatch.setattr(vc, "_valid_jwt", lambda: _make_jwt(exp=time.time() + 3600))
    monkeypatch.setattr(vc, "_device_headers", lambda: {"X-Voxis-Device-Primary": "g"})
    seen = {}

    class _FakeHttp:
        def get(self, url, headers=None, params=None, timeout=None):
            seen["url"] = url
            seen["headers"] = headers
            return _FakeResp(200, {"key": "k", "engine": "gemini"})

    monkeypatch.setattr(vc, "_http", _FakeHttp())
    key, engine, *_rest, err = vc.get_session_key(target="cs", caps="engine-routing")
    assert (key, engine, err) == ("k", "gemini", None)
    assert seen["url"].endswith("/auth/session-key")
    # Auth header intact, device fingerprint riding alongside it.
    assert seen["headers"]["Authorization"].startswith("Bearer ")
    assert seen["headers"]["X-Voxis-Device-Primary"] == "g"


def _fake_get(monkeypatch, resp):
    monkeypatch.setattr(vc, "IS_OFFICIAL_RELEASE", True)
    monkeypatch.setattr(vc, "_valid_jwt", lambda: _make_jwt(exp=time.time() + 3600))

    class _FakeHttp:
        def get(self, url, headers=None, params=None, timeout=None):
            return resp

    monkeypatch.setattr(vc, "_http", _FakeHttp())


def test_session_key_plain_quota_exhausted_still_returns_tuple(monkeypatch):
    # A 402 with no free_reused flag is the ordinary out-of-quota case — must
    # keep returning the (None, ..., error) tuple every caller already expects,
    # not raise. Confirms the new branch doesn't widen the exception surface.
    _fake_get(monkeypatch, _FakeResp(402, {"error": "quota exceeded"}))
    key, *_rest, err = vc.get_session_key()
    assert key is None
    assert err  # localized message, non-empty

    # Also true for a 402 with an unparsable/empty body (old server, or a
    # transport that returns no JSON at all).
    class _BadJSON(_FakeResp):
        def json(self):
            raise ValueError("no body")

    _fake_get(monkeypatch, _BadJSON(402))
    key, *_rest, err = vc.get_session_key()
    assert key is None and err


def test_session_key_device_blocked_raises_with_hint(monkeypatch):
    _fake_get(monkeypatch, _FakeResp(402, {
        "error": "quota exceeded",
        "free_reused": True,
        "first_account": "su***@gmail.com",
        "first_account_remaining_min": 30.0,
    }))
    with pytest.raises(vc.DeviceBlockedError) as exc_info:
        vc.get_session_key()
    err = exc_info.value
    assert err.first_account == "su***@gmail.com"
    assert err.remaining_minutes == 30.0
    assert str(err)  # localized message, non-empty


def test_session_key_device_blocked_without_hint_still_raises(monkeypatch):
    # Server resolved free_reused but couldn't resolve the other account
    # (older license, lookup miss) — still the specific exception, with both
    # hint fields None so the UI falls back to the generic status line.
    _fake_get(monkeypatch, _FakeResp(402, {"free_reused": True}))
    with pytest.raises(vc.DeviceBlockedError) as exc_info:
        vc.get_session_key()
    assert exc_info.value.first_account is None
    assert exc_info.value.remaining_minutes is None


# --- get_quota: the 401 that froze the minutes-left counter ---------------
#
# /auth/quota only READS the server's 5-minute token cache, so it 401s once per
# TTL by construction. get_quota used to map that to None, and the UI keeps its
# previous value when a poll yields nothing — so the counter froze at a stale
# number for the rest of a long session (field report, 2026-07-28).


def _quota_env(monkeypatch, gets, verify_result=None):
    """Official build, valid JWT, scripted GET responses, stubbed verify."""
    monkeypatch.setattr(vc, "IS_OFFICIAL_RELEASE", True)
    monkeypatch.setattr(vc, "_valid_jwt", lambda: _make_jwt(exp=time.time() + 3600))
    monkeypatch.setattr(vc, "_last_quota_reauth_fail", 0.0)
    calls = {"gets": 0, "verifies": 0}

    class _FakeHttp:
        def get(self, url, headers=None, params=None, timeout=None):
            calls["gets"] += 1
            return gets[min(calls["gets"] - 1, len(gets) - 1)]

    def _verify():
        calls["verifies"] += 1
        return verify_result if verify_result is not None else (None, "err")

    monkeypatch.setattr(vc, "_http", _FakeHttp())
    monkeypatch.setattr(vc, "verify_session", _verify)
    return calls


def test_get_quota_200_does_not_reverify(monkeypatch):
    fresh = {"remaining": 60.0, "allowed_minutes": 380.0, "used_minutes": 320.0}
    calls = _quota_env(monkeypatch, [_FakeResp(200, fresh)])
    assert vc.get_quota() == fresh
    assert calls["gets"] == 1 and calls["verifies"] == 0


def test_get_quota_401_reverifies_and_returns_fresh_snapshot(monkeypatch):
    # The regression: cache expired mid-session. /auth/verify repopulates it and
    # answers with the same snapshot shape, so its body IS the fresh quota — the
    # counter must move, not hold its last number.
    fresh = {"remaining": 0.0, "allowed_minutes": 380.0, "used_minutes": 380.1}
    calls = _quota_env(monkeypatch, [_FakeResp(401)], verify_result=(fresh, None))
    assert vc.get_quota() == fresh
    assert calls["verifies"] == 1


def test_get_quota_401_then_402_verify_retries_the_read(monkeypatch):
    # A paid tier that is genuinely exhausted: /auth/verify 402s (verify_session
    # returns None) but resolveEntry already re-cached the entry on the way
    # there, so one retry of the GET yields the exhausted snapshot the counter
    # has to display.
    exhausted = {"remaining": 0.0, "allowed_minutes": 380.0, "used_minutes": 380.1}
    calls = _quota_env(monkeypatch, [_FakeResp(401), _FakeResp(200, exhausted)],
                       verify_result=(None, "quota exceeded"))
    assert vc.get_quota() == exhausted
    assert calls["gets"] == 2 and calls["verifies"] == 1


def test_get_quota_failed_reverify_is_throttled(monkeypatch):
    # PB down: verify fails and the retry 401s too. The next poll (6 s later)
    # must NOT re-verify again — three requests every six seconds against an
    # already-sick server is how a stale counter becomes an outage amplifier.
    calls = _quota_env(monkeypatch, [_FakeResp(401)], verify_result=(None, "502"))
    assert vc.get_quota() is None
    assert calls["verifies"] == 1
    assert vc.get_quota() is None
    assert calls["verifies"] == 1, "failed re-verify must be throttled"


def test_get_quota_non_401_error_never_reverifies(monkeypatch):
    # 500/403/transport failure is not a cache miss — returning None there is
    # correct and must not cost an extra round-trip.
    calls = _quota_env(monkeypatch, [_FakeResp(500)])
    assert vc.get_quota() is None
    assert calls["gets"] == 1 and calls["verifies"] == 0


# --- get_referral_info: OSS/dev build never reaches the network -----------


def test_get_referral_info_disabled_on_oss_build(monkeypatch):
    monkeypatch.setattr(vc, "IS_OFFICIAL_RELEASE", False)
    calls = {"gets": 0}

    class _FakeHttp:
        def get(self, *a, **kw):
            calls["gets"] += 1
            return _FakeResp(200, {})

    monkeypatch.setattr(vc, "_http", _FakeHttp())
    info, err = vc.get_referral_info()
    assert info is None
    assert err  # localized message, non-empty
    assert calls["gets"] == 0
