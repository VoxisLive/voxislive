#!/usr/bin/env python3
"""commit-msg hook: strip any Claude/Anthropic Co-Authored-By trailer.

This repo must never show Claude/Anthropic as a GitHub contributor — see
.vault/no-claude-attribution-public-repo.md for the full history of why
(the trailer slipped through 5 times despite a standing memory rule).
Installed by scripts/install_hooks.py. Silently drops the offending line(s)
instead of blocking the commit, since the trailer is auto-added by the
default Claude Code commit workflow rather than typed by a human.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(r"^co-authored-by:.*(claude|anthropic).*$", re.IGNORECASE)


def main() -> int:
    msg_path = Path(sys.argv[1])
    lines = msg_path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if not PATTERN.match(ln.strip())]
    if kept != lines:
        while kept and kept[-1].strip() == "":
            kept.pop()
        msg_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        print("commit-msg hook: stripped a Claude/Anthropic co-author trailer", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
