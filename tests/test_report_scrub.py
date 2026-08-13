"""app/report_scrub.py -- the fail-closed redaction applied to every
'Report a problem' payload before it leaves the device (see that module's
docstring). Had zero test coverage despite being the one thing standing
between a pasted transcript/log and a leaked JWT, API key, or Windows
account name -- these pin both the redaction patterns and the fail-closed
contract (a value that can't be scrubbed must never ship raw)."""
from app import report_scrub

# --- scrub_text ------------------------------------------------------------

def test_scrub_text_passthrough_non_string():
    assert report_scrub.scrub_text(None) is None
    assert report_scrub.scrub_text(42) == 42
    assert report_scrub.scrub_text("") == ""


def test_scrub_text_leaves_ordinary_text_unchanged():
    s = "Voxis stopped translating after about 30 seconds, no error shown."
    assert report_scrub.scrub_text(s) == s


def test_scrub_text_redacts_jwt_with_and_without_bearer_prefix():
    # jwt.io's canonical sample token (public documentation example, not a
    # live credential) -- flagged as "example" so the release-hygiene secret
    # scanner (scripts/check_release_hygiene.py PLACEHOLDER_HINTS) skips it.
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w"  # example
    assert report_scrub.scrub_text(f"token={jwt}") == "token=[REDACTED_JWT]"
    assert report_scrub.scrub_text(f"Authorization: Bearer {jwt}") == \
        "Authorization: [REDACTED_JWT]"


def test_scrub_text_redacts_google_api_key():
    key = "AIza" + "A" * 35
    assert report_scrub.scrub_text(f"key was {key} in the log") == \
        "key was [REDACTED_KEY] in the log"


def test_scrub_text_redacts_aws_access_key():
    key = "AKIA" + "Q" * 16
    assert report_scrub.scrub_text(f"aws creds {key} leaked") == \
        "aws creds [REDACTED_KEY] leaked"


def test_scrub_text_redacts_generic_secret_assignment():
    s = "config had api_key: sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    assert report_scrub.scrub_text(s) == "config had [REDACTED_SECRET]"


def test_scrub_text_redacts_generic_secret_natural_language_phrasing():
    # "X is Y" (no colon/equals) is how a non-technical user actually types
    # this in a free-text field, not "key: value".
    s = "my api key is ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 and it stopped working"
    assert report_scrub.scrub_text(s) == \
        "my [REDACTED_SECRET] and it stopped working"


def test_scrub_text_redacts_bare_dashscope_key_with_no_label():
    # DashScope (Qwen BYOK) keys use the "sk-..." shape (see
    # build_official.py's _SEED_KEY_SHAPES) -- a bare paste with no "key:"
    # prefix at all must still be caught.
    key = "sk-" + "a1B2c3D4e5F6g7H8i9J0" * 2
    assert report_scrub.scrub_text(f"here it is: {key}") == \
        "here it is: [REDACTED_KEY]"


def test_scrub_text_redacts_email():
    assert report_scrub.scrub_text("contact me at drypts@icloud.com please") == \
        "contact me at [REDACTED_EMAIL] please"


def test_scrub_text_normalizes_windows_user_path_backslash():
    s = r"log lives at C:\Users\JohnDoe\AppData\Local\Voxis\voxis.log"
    assert report_scrub.scrub_text(s) == \
        r"log lives at C:\Users\<user>\AppData\Local\Voxis\voxis.log"


def test_scrub_text_normalizes_windows_user_path_forward_slash_and_case():
    # Lowercase drive/segment, forward slashes -- (?i) covers the whole match.
    s = "c:/users/johndoe/Documents/file.txt"
    assert report_scrub.scrub_text(s) == "c:/users/<user>/Documents/file.txt"


def test_scrub_text_never_raises_fail_closed(monkeypatch):
    class _RaisingPattern:
        def sub(self, repl, s):
            raise RuntimeError("boom")

    monkeypatch.setattr(report_scrub, "_SUBS", [(_RaisingPattern(), "x")])
    assert report_scrub.scrub_text("anything at all") == report_scrub._REDACTED


# --- scrub_value -------------------------------------------------------------

def test_scrub_value_denylist_redacts_whole_value_regardless_of_type():
    payload = {
        "api_key": "should-not-appear",
        "Authorization": "Bearer abc123",
        "password": {"nested": "still gone"},
        "cookie": ["a", "b"],
        "MachineGuid": "1234-5678",
    }
    out = report_scrub.scrub_value(payload)
    for key in payload:
        assert out[key] == report_scrub._REDACTED


def test_scrub_value_denylist_is_substring_match_by_design():
    # _DENY_KEY is `.search`, not an exact match -- "session_id" and
    # "device_id_hash" both trip it via "session"/"device_id". Pinned
    # deliberately: this is documented, non-obvious over-redaction, not a bug.
    out = report_scrub.scrub_value({"session_id": "s-1", "device_id_hash": "d-1"})
    assert out["session_id"] == report_scrub._REDACTED
    assert out["device_id_hash"] == report_scrub._REDACTED


def test_scrub_value_scrubs_string_values_via_layer_b_on_safe_keys():
    out = report_scrub.scrub_value({"user_note": "reach me at a@b.com"})
    assert out["user_note"] == "reach me at [REDACTED_EMAIL]"


def test_scrub_value_recurses_into_nested_dicts_and_lists():
    payload = {
        "items": [1, "safe text", "user@example.com"],
        "nested": {"deep": {"email": "x@y.com"}},
    }
    out = report_scrub.scrub_value(payload)
    assert out["items"] == [1, "safe text", "[REDACTED_EMAIL]"]
    assert out["nested"]["deep"]["email"] == "[REDACTED_EMAIL]"


def test_scrub_value_tuple_becomes_list():
    out = report_scrub.scrub_value((1, 2, "x@y.com"))
    assert out == [1, 2, "[REDACTED_EMAIL]"]


def test_scrub_value_passthrough_scalars():
    assert report_scrub.scrub_value(7) == 7
    assert report_scrub.scrub_value(1.5) == 1.5
    assert report_scrub.scrub_value(True) is True
    assert report_scrub.scrub_value(None) is None


def test_scrub_value_never_raises_fail_closed():
    class _RaisingMapping(dict):
        def items(self):
            raise RuntimeError("boom")

    assert report_scrub.scrub_value(_RaisingMapping()) == report_scrub._REDACTED


def test_scrub_schema_constant_is_stable():
    # webui.py stamps this onto every outgoing report payload; a silent bump
    # here without updating the server-side consumer is the failure mode
    # this pins against.
    assert report_scrub.SCRUB_SCHEMA == "scrub-v1"
