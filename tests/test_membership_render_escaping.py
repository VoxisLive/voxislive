"""renderMembership() (app.js) builds its plan-name label from the server's
quota response: `tier = q.tier || q.plan`, looked up against a fixed
{free,creator,pro,enterprise} map. An unrecognized value used to fall through
to echoing the RAW server string (capitalized) straight into an innerHTML=
assignment -- a server bug/anomaly returning e.g. an unexpected `tier` field
would inject markup into the main window. This pins the fix: the fallback
branch must run through escHtml() before it can reach innerHTML.
"""
from pathlib import Path

WEB_DIR = Path(__file__).parents[1] / "app" / "web"
APP_JS = (WEB_DIR / "app.js").read_text(encoding="utf-8")


def test_tier_name_fallback_is_escaped_before_use():
    assert "escHtml(tier.charAt(0).toUpperCase()+tier.slice(1))" in APP_JS


def test_tier_name_fallback_no_longer_echoes_raw_server_value():
    # The pre-fix line concatenated the raw fallback directly with no escHtml
    # call around it -- assert that unescaped shape is gone.
    assert "|| (tier.charAt(0).toUpperCase()+tier.slice(1))" not in APP_JS
