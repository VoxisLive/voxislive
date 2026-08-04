"""Generate app.json: the single published source for the app's version and
language coverage, consumed by (1) the desktop client's update-available check
and (2) voxislive.com's marketing copy — so a language added/removed here never
needs a second, hand-edited update anywhere else.

Reads, never redeclares:
  - app.APP_VERSION
  - app.config.LANGS               (the 79-target picker list, SSOT)
  - app.web.index.html LANG_NAMES  (endonym labels, parsed via node — same
                                     brace-matching approach as check_i18n.py)
  - app.local_tts.VOICES           (which of LANGS the free tier can speak)

Run: `python scripts/gen_app_manifest.py [output_path]`
Default output: .local/site-data/app.json (gitignored; deploy to the site by
hand or from the voxis-build release chain).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import APP_VERSION  # noqa: E402
from app.config import LANGS  # noqa: E402
from app import local_tts  # noqa: E402

DEFAULT_OUTPUT = os.path.join(ROOT, ".local", "site-data", "app.json")

# node: string-aware brace-match `const LANG_NAMES = {...}` and emit it as JSON.
# Mirrors scripts/check_i18n.py's extract() so both scripts stay in lockstep if
# index.html's object-literal style ever changes.
_NODE = r"""
const fs = require('fs');
const s = fs.readFileSync(process.argv[1], 'utf8');
const anchor = 'const LANG_NAMES =';
const m = s.indexOf(anchor);
if (m < 0) throw new Error('not found: ' + anchor);
const i = s.indexOf('{', m);
let depth = 0, q = null, esc = false;
for (let j = i; j < s.length; j++){
  const c = s[j];
  if (esc){ esc = false; continue; }
  if (q){ if (c === '\\') esc = true; else if (c === q) q = null; continue; }
  if (c === '"' || c === "'" || c === '`'){ q = c; continue; }
  if (c === '{') depth++;
  else if (c === '}' && --depth === 0){
    process.stdout.write(JSON.stringify(eval('(' + s.slice(i, j + 1) + ')')));
    process.exit(0);
  }
}
throw new Error('unbalanced: ' + anchor);
"""


def _lang_names():
    """{code: endonym} from index.html. Raises if node is unavailable or the
    object can't be parsed — an app.json with wrong/missing names is worse than
    a build that fails loudly, unlike check_i18n.py's soft-skip (that's a lint
    warning; this writes a file real consumers read)."""
    node = next((c for c in ("node", "node.exe") if _has(c)), None)
    if node is None:
        raise RuntimeError("node is required to parse LANG_NAMES out of index.html")
    html = os.path.join(ROOT, "app", "web", "index.html")
    r = subprocess.run([node, "-e", _NODE, html], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"LANG_NAMES parse failed: {(r.stderr or '').strip()[:300]}")
    return json.loads(r.stdout)


def _has(cmd):
    try:
        return subprocess.run([cmd, "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


def build_manifest():
    names = _lang_names()
    translation = [{"code": c, "name": names.get(c, c)} for c in LANGS]
    voiced_free = [{"code": c, "name": names.get(c, c)}
                   for c in LANGS if local_tts.voice_available(c)]
    return {
        "schema_version": 1,
        "app": {
            "version": APP_VERSION,
            "links": {
                "microsoft_store": "ms-windows-store://pdp/?productid=9P5Z0KVS58RS",
                "chrome_extension": "https://chromewebstore.google.com/detail/voxis-%E2%80%94-live-translate/eaoplhkoomnlgfhcjeccgkhnkodkfbjn",
            },
        },
        "languages": {
            "translation_total": len(translation),
            "translation": translation,
            "voiced_pro_total": len(translation),
            "voiced_free_total": len(voiced_free),
            "voiced_free": voiced_free,
        },
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    manifest = build_manifest()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {out_path}")
    print(f"  version={manifest['app']['version']}  "
          f"translation={manifest['languages']['translation_total']}  "
          f"voiced_free={manifest['languages']['voiced_free_total']}")


if __name__ == "__main__":
    main()
