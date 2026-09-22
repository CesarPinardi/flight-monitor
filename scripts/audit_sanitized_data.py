#!/usr/bin/env python3
"""Reject secrets in persisted monitor data, generated site files, or logs."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys


PATTERNS = (
    re.compile(r"SERPAPI_API_KEY\s*=\s*[^\s\"']+"),
    re.compile(r"TELEGRAM_BOT_TOKEN\s*=\s*[^\s\"']+"),
    re.compile(r"TELEGRAM_CHAT_ID\s*=\s*[^\s\"']+"),
    re.compile(r"https://api\.telegram\.org/bot[0-9]+:[A-Za-z0-9_-]+"),
)
SECRET_NAMES = ("SERPAPI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def main(argv: list[str]) -> int:
    paths = [Path(value) for value in argv[1:]]
    failures: list[str] = []
    secret_values = [os.getenv(name, "").strip() for name in SECRET_NAMES]
    secret_values = [value for value in secret_values if value]
    for path in paths:
        if not path.exists():
            continue
        if not path.is_file():
            failures.append(f"not a file: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(value in text for value in secret_values):
            failures.append(f"secret value found: {path}")
        if any(pattern.search(text) for pattern in PATTERNS):
            failures.append(f"secret-shaped value found: {path}")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"secret audit passed ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
