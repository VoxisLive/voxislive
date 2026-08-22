#!/usr/bin/env python3
"""Release hygiene gate for the public (source-available) Voxis repository.

Purpose
-------
This repository publishes a small, curated, explicitly-allowlisted slice of
the real Voxis engine — the audio capture -> translate -> playback -> local
storage chain — so it can be read and audited. It is NOT the product source,
NOT a build target, and NOT open source in the "clone and run" sense (see
LICENSE and README.md). Almost everything about the real application —
orchestration, the UI, the paid engines, business logic, auth — lives in a
private repository and must never appear here.

Unlike a typical open-source hygiene gate that blocks a short list of
forbidden paths, this one is a strict ALLOWLIST: every tracked path must be
named exactly in PUBLIC_EXACT_FILES below, or it is rejected. This is
deliberate friction — adding anything to the public surface requires a
conscious edit to this file, not just an accidental `git add`.

What it checks
---------------
1. Allowlist            — every tracked path is one of the exact files named
   below; anything else (a whole new file, a renamed file, a moved file) is
   rejected by default.
2. Secret content scan  — tracked text files carry no live credentials.
3. (optional) history scan — the same signatures never appear in git
   history, AND no non-allowlisted path ever existed in history.

It is dependency-free (stdlib only) so it runs identically on the
maintainer's machine (pre-push hook) and in GitHub Actions. Exit code is 0
when clean, 1 on any violation.

Usage
-----
    python scripts/check_release_hygiene.py            # scan the tracked tree
    python scripts/check_release_hygiene.py --history  # also scan git history
    python scripts/check_release_hygiene.py --staged   # scan only staged files
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# --- Public surface -----------------------------------------------------------
# The COMPLETE list of paths allowed to be tracked in this repository. Anything
# not named here is rejected, regardless of which directory it sits under.
PUBLIC_EXACT_FILES = frozenset({
    ".gitattributes", ".gitignore", "CHANGELOG.md", "LICENSE",
    "README.md", "README.de.md", "README.tr.md", "pyrightconfig.json",

    "app/__init__.py",
    "app/i18n.py",
    "app/process_loopback.py",
    "app/session_duck.py",
    "app/win_audio.py",
    "app/audio_io.py",
    "app/mix_core.py",
    "app/vad.py",
    "app/base_translator.py",
    "app/translator.py",
    "app/audio_recorder.py",
    "app/transcript_store.py",
    "app/report_scrub.py",
    "app/paths.py",

    "docs/PRIVACY.md",
    "docs/TERMS.md",
    "docs/EULA.md",
    "docs/REFUND.md",
    "docs/AI_DISCLOSURE.md",
    "docs/MEETING_CONSENT.md",
    "docs/VOICE_CREDITS.md",

    "scripts/check_release_hygiene.py",

    "tests/conftest.py",
    "tests/test_audio_test_tone.py",
    "tests/test_mix_core.py",
    "tests/test_report_scrub.py",
    "tests/test_player_volume.py",
    "tests/test_ring.py",
    "tests/test_session_duck.py",
    "tests/test_speech_gate.py",
    "tests/test_transcript_export.py",
    "tests/test_audio_recorder.py",

    ".github/CODE_OF_CONDUCT.md",
    ".github/SECURITY.md",
    ".github/CONTRIBUTING.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/workflows/release-hygiene.yml",
    ".github/workflows/quality.yml",
})

# Paths consciously grandfathered in public history (a force-push rewrite to
# remove them would break every clone and fork). Empty — this repo's history
# was squashed to a single curated commit when it was narrowed; add entries
# here only for a *future* leak judged not worth another rewrite.
HISTORY_PATH_ALLOWLIST: frozenset[str] = frozenset()
HISTORY_PATH_ALLOWLIST_PREFIXES: tuple[str, ...] = ()
HISTORY_SECRET_ALLOWLIST: frozenset[str] = frozenset()

# --- Secret content signatures ----------------------------------------------
SECRET_PATTERNS = (
    ("Google/Gemini API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}")),
    ("Stripe webhook secret", re.compile(r"\bwhsec_[0-9A-Za-z]{16,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("Device pepper value", re.compile(r"(?i)\bDEVICE_PEPPER\b\s*[:=]\s*['\"][^'\"\s]{6,}['\"]")),
    ("Hard-coded JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Resend API key", re.compile(r"\bre_[0-9A-Za-z]{16,}")),
)

PLACEHOLDER_HINTS = ("...", "…", "EXAMPLE", "example", "your-", "<", "xxxx", "XXXX")

BINARY_EXT = {".ico", ".png", ".jpg", ".jpeg", ".gif", ".onnx", ".pyc", ".so",
              ".dll", ".exe", ".zip", ".gz", ".woff", ".woff2", ".ttf", ".otf"}


def _load_private_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Forbidden literals supplied out-of-tree (env var + .git private file)."""
    literals: list[str] = []
    env = os.environ.get("VOXIS_HYGIENE_EXTRA", "")
    for chunk in env.replace(",", "\n").splitlines():
        s = chunk.strip()
        if s:
            literals.append(s)
    root = Path(__file__).resolve().parent.parent
    try:
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=root,
            capture_output=True, text=True,
        ).stdout.strip()
        priv = (root / git_dir / "voxis-hygiene-private").resolve()
        if priv.exists():
            for line in priv.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    literals.append(s)
    except OSError:
        pass
    return [("Private forbidden literal", re.compile(re.escape(s))) for s in literals]


def _git(*args: str) -> str:
    root = Path(__file__).resolve().parent.parent
    out = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{out.stderr.strip()}")
    return out.stdout


def tracked_files(staged_only: bool) -> list[str]:
    if staged_only:
        raw = _git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    else:
        raw = _git("ls-files")
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def _forbidden_path_label(norm: str) -> str | None:
    """Return a human label if `norm` is outside the public allowlist, else None."""
    if norm not in PUBLIC_EXACT_FILES:
        return "path not on the public allowlist"
    return None


def check_paths(files: list[str]) -> list[str]:
    violations = []
    for f in files:
        norm = f.replace("\\", "/")
        label = _forbidden_path_label(norm)
        if label:
            violations.append(f"tracked {label}: {norm}")
    return violations


def _read_text(path: Path) -> str | None:
    if path.suffix.lower() in BINARY_EXT:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def scan_content(files: list[str], patterns) -> list[str]:
    root = Path(__file__).resolve().parent.parent
    violations = []
    for f in files:
        text = _read_text(root / f)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in patterns:
                m = pat.search(line)
                if not m:
                    continue
                if any(h in line for h in PLACEHOLDER_HINTS):
                    continue
                snippet = m.group(0)
                redacted = snippet[:6] + "…" if len(snippet) > 6 else snippet
                violations.append(f"{f}:{lineno}: {label} -> {redacted}")
    return violations


def scan_history(patterns) -> list[str]:
    # Scoped to this branch's own history (HEAD), not --all: old release tags
    # from before this repository was narrowed to an allowlisted excerpt still
    # point at commits with the full prior source (GitHub Immutable Releases
    # make those tags undeletable) — that's a known, accepted residual (see
    # README.md), not something this gate should re-flag on every run.
    diff = _git("log", "-p")
    violations = []
    for line in diff.splitlines():
        if not line.startswith("+"):
            continue
        for label, pat in patterns:
            m = pat.search(line)
            if (m and not any(h in line for h in PLACEHOLDER_HINTS)
                    and m.group(0) not in HISTORY_SECRET_ALLOWLIST):
                violations.append(f"history: {label} -> {m.group(0)[:6]}…")
    return violations


def scan_history_paths() -> list[str]:
    # Scoped to HEAD, not --all — see the comment in scan_history() above.
    raw = _git("log", "--pretty=format:", "--name-only")
    seen: set[str] = set()
    violations = []
    for line in raw.splitlines():
        norm = line.strip().replace("\\", "/")
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if norm in HISTORY_PATH_ALLOWLIST or norm.startswith(HISTORY_PATH_ALLOWLIST_PREFIXES):
            continue
        label = _forbidden_path_label(norm)
        if label:
            violations.append(f"{label} in history: {norm}")
    return violations


def main() -> int:
    ap = argparse.ArgumentParser(description="Public-repo release hygiene gate.")
    ap.add_argument("--history", action="store_true", help="also scan git history")
    ap.add_argument("--staged", action="store_true", help="scan only staged files")
    args = ap.parse_args()

    patterns = SECRET_PATTERNS + tuple(_load_private_patterns())
    files = tracked_files(args.staged)
    path_violations = check_paths(files)
    content_violations = scan_content(files, patterns)
    history_violations = scan_history(patterns) if args.history else []
    history_path_violations = scan_history_paths() if args.history else []

    all_violations = (
        [("NOT ALLOWLISTED", v) for v in path_violations]
        + [("LIVE SECRET", v) for v in content_violations]
        + [("HISTORY SECRET", v) for v in history_violations]
        + [("HISTORY PATH", v) for v in history_path_violations]
    )

    scope = "staged files" if args.staged else f"{len(files)} tracked files"
    print(f"Voxis release hygiene gate — scanned {scope}"
          + (" + git history" if args.history else ""))

    if not all_violations:
        print("OK: public surface matches the allowlist. No live secrets.")
        return 0

    print(f"\nBLOCKED: {len(all_violations)} violation(s) — these must not reach GitHub:\n")
    for kind, detail in all_violations:
        print(f"  [{kind}] {detail}")
    print("\nRefusing to certify this tree for public push.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
