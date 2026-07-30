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
notes_1050.json). Only that one version is kept in the table — the card only ever
shows the running version, and old entries would just be dead weight in the
bundle. Pass --keep to append instead of replacing.
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
