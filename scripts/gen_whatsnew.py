"""Regenerate app/whatsnew.py from the release's Store-listing notes.

The release chain already writes `.local/store-listings/notes_<ver>.json` — the
same "what's new" text, translated into all 23 Store locales. This maps those
locales onto the app's own language codes and rewrites the NOTES table, so the
in-app card and the Store listing can never tell users different things and
nobody translates the same three bullets twice.

Run it in the release chain right after the notes JSON is written:

    python scripts/gen_whatsnew.py 1.0.50

The version argument is the APP_VERSION the notes belong to; the JSON filename is
derived from it the way the rest of the chain does (dots stripped: 1.0.50 ->
notes_1050.json).

Pass --keep (what the release chain uses) to ADD this version to the table
instead of replacing it. The card shows every version the user skipped, not just
the running one — Store updates jump versions freely, and a one-version table is
what made 1.0.50's notes reach nobody who went 1.0.49 -> 1.0.51 in a single
background update. Only the newest KEEP_VERSIONS entries survive, so the table
covers realistic skips without growing forever inside the bundle.
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "app", "whatsnew.py")
NOTES_DIR = os.path.join(ROOT, ".local", "store-listings")

# Store listing locale -> the app's own language code (app/i18n.py STRINGS keys).
# pt-BR carries Portuguese for the app's single "pt"; zh-CN/zh-TW split onto the
# app's zh / zh-Hant, which are genuinely separate UI languages.
LOCALE_MAP = {
    "cs-CZ": "cs", "de-DE": "de", "en-US": "en", "es-ES": "es", "fr-FR": "fr",
    "hi-IN": "hi", "hu-HU": "hu", "id-ID": "id", "it-IT": "it", "ja-JP": "ja",
    "ko-KR": "ko", "nl-NL": "nl", "pl-PL": "pl", "pt-BR": "pt", "ro-RO": "ro",
    "ru-RU": "ru", "sr-Latn-RS": "sr", "sv-SE": "sv", "th-TH": "th",
    "tr-TR": "tr", "vi-VN": "vi", "zh-CN": "zh", "zh-TW": "zh-Hant",
}


# How many versions the in-app table carries. Five covers a user who ignored
# updates for a while without turning the bundle into an archive; anyone further
# behind gets the full history from the site's changelog page (linked in the card).
KEEP_VERSIONS = 5


def _ver_key(version: str) -> tuple:
    """Numeric version key — string order puts "1.0.9" after "1.0.10"."""
    return tuple(int("".join(c for c in part if c.isdigit()) or 0)
                 for part in str(version).split("."))


def bullets(block: str) -> list:
    """The '•' lines of one listing note block, without the title line."""
    out = []
    for line in (block or "").splitlines():
        line = line.strip()
        if line.startswith("•"):
            out.append(line.lstrip("•").strip())
    return out


def build(version: str, keep: bool) -> str:
    path = os.path.join(NOTES_DIR, f"notes_{version.replace('.', '')}.json")
    if not os.path.exists(path):
        raise SystemExit(f"no listing notes for {version}: {path}")
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    per_lang = {}
    for fname, block in raw.items():
        lang = LOCALE_MAP.get(fname[:-3] if fname.endswith(".md") else fname)
        if lang and bullets(block):
            per_lang[lang] = bullets(block)

    from app import i18n  # noqa: PLC0415 - after ROOT is on sys.path
    missing = sorted(set(i18n.STRINGS) - set(per_lang))
    if missing:
        # Not fatal: entry() falls back to English. But it IS drift, and the
        # release should hear about it rather than ship a half-translated card.
        print(f"  WARN  no notes for: {', '.join(missing)} (they will read English)")
    if "en" not in per_lang:
        raise SystemExit("no en-US notes — English is the fallback, refusing to write")

    src = open(TARGET, encoding="utf-8").read()
    existing = {}
    if keep:
        from app import whatsnew  # noqa: PLC0415
        existing = {v: d for v, d in whatsnew.NOTES.items() if v != version}
        # Keep the newest few and drop the rest: enough to cover a user who
        # skipped several Store updates, bounded so the table cannot grow with
        # every release. Sorted numerically — "1.0.9" beats "1.0.10" as a string.
        table = dict(sorted({**existing, version: per_lang}.items(),
                            key=lambda kv: _ver_key(kv[0]))[-KEEP_VERSIONS:])
        dropped = sorted(set(existing) - set(table), key=_ver_key)
        if dropped:
            print(f"  trim  dropped older notes: {', '.join(dropped)}")
        existing = {v: d for v, d in table.items() if v != version}

    out = io.StringIO()
    out.write("NOTES = {\n")
    for ver, langs in list(existing.items()) + [(version, per_lang)]:
        out.write(f'    "{ver}": {{\n')
        for lang, items in langs.items():
            out.write(f'        "{lang}": [\n')
            for b in items:
                out.write("            " + json.dumps(b, ensure_ascii=False) + ",\n")
            out.write("        ],\n")
        out.write("    },\n")
    out.write("}\n")

    start = src.index("NOTES = {")
    end = src.index("\n}\n", start) + 3
    return src[:start] + out.getvalue() + src[end:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", help="APP_VERSION the notes belong to, e.g. 1.0.50")
    ap.add_argument("--keep", action="store_true",
                    help="keep other versions already in the table")
    args = ap.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise SystemExit(f"not a version: {args.version}")

    sys.path.insert(0, ROOT)
    text = build(args.version, args.keep)
    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"  OK    app/whatsnew.py rewritten for {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
