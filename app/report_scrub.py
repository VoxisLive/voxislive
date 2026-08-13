"""Client-side scrub (scrub-v1) for the 'Report a problem' channel.

Secrets and the Windows username must leave the device already redacted — the
server scrub is only a backstop. Two layers run over the assembled payload before
it is serialized for transport:

  * Layer A — denylist by key name: any mapping key that names a credential is
    redacted whole (a future field that happens to carry a token can't leak).
  * Layer B — regex over every string value: JWTs, API keys and stray emails are
    replaced with fixed tokens; ``C:\\Users\\<name>\\`` paths are normalized so the
    account name never ships.

Fail-closed: if scrubbing a value raises, the value is dropped rather than sent.
"""
import re

SCRUB_SCHEMA = "scrub-v1"

# Layer A — redact the whole value when the key names a secret.
_DENY_KEY = re.compile(
    r"(api[_-]?key|apikey|^key$|token|jwt|authorization|auth|bearer|secret|"
    r"password|passwd|credential|cookie|session|machineguid|fingerprint|device_id)",
    re.IGNORECASE,
)

# Layer B — value-level redactions. Order matters: JWT before generic key=.
_SUBS = [
    (re.compile(r"(?:Bearer\s+)?eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), "[REDACTED_JWT]"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "[REDACTED_KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_KEY]"),
    # Generic "key/secret/token" + value, tolerating how people actually type
    # it ("api key is X", "secret: X", "token=X") rather than only key[:=]value.
    # Runs before the bare sk- pattern below so a labeled "api_key: sk-..."
    # gets consumed whole (label included) instead of leaving the label as
    # visible leftover text around a narrower [REDACTED_KEY].
    (re.compile(r"(?i)(?:api[\s_-]?key|secret|token)\s*(?:[:=]|is)\s*[\"']?[A-Za-z0-9_\-]{16,}"), "[REDACTED_SECRET]"),
    # DashScope (Qwen) key shape -- same "sk-..." pattern build_official.py's
    # _SEED_KEY_SHAPES already treats as a real key, but that scanner only
    # guards the shipped seed config; this is the only thing standing between
    # a raw pasted BYOK Qwen key and the report server, so it needs the same
    # pattern independently (no label required -- a bare "sk-..." paste in a
    # free-text field carries no "key:" prefix to key off of).
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
]

# Path normalization: strip the Windows account name out of any user-profile path
# (handles both back- and forward-slash forms, case-insensitively).
_USER_PATH = re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/]+")
_REDACTED = "[dropped]"


def scrub_text(s):
    """Apply every value-level redaction + path normalization. Never raises."""
    if not isinstance(s, str) or not s:
        return s
    try:
        for pat, repl in _SUBS:
            s = pat.sub(repl, s)
        s = _USER_PATH.sub(r"\1<user>", s)
        return s
    except Exception:
        # Fail-closed: a value we couldn't scrub must not ship raw.
        return _REDACTED


def scrub_value(value, *, _key=None):
    """Recursively scrub a JSON-serializable value.

    Mappings get Layer A (key denylist) + recursion; strings get Layer B.
    A scrub that raises drops that node to a redaction marker (fail-closed)."""
    try:
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if isinstance(k, str) and _DENY_KEY.search(k):
                    out[k] = _REDACTED
                else:
                    out[k] = scrub_value(v, _key=k)
            return out
        if isinstance(value, (list, tuple)):
            return [scrub_value(v) for v in value]
        if isinstance(value, str):
            return scrub_text(value)
        # int / float / bool / None pass through unchanged.
        return value
    except Exception:
        return _REDACTED
