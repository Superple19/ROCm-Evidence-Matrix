from __future__ import annotations

import re
import sys
from pathlib import Path


COMMIT_TYPES = "build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test"
SUBJECT = re.compile(rf"^(?:{COMMIT_TYPES})(?:\([^\)]+\))?: \S.*$")


def validate_message(text: str) -> str | None:
    if "\\n" in text or "\\r" in text:
        return "commit message must use real line breaks, not escaped \\n or \\r"
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines or not lines[0].strip():
        return "commit subject is required"
    if lines[0] != lines[0].rstrip():
        return "commit subject must not have trailing whitespace"
    if not SUBJECT.fullmatch(lines[0]):
        return "subject must use type(scope): description"
    if len(lines) < 3 or lines[1] != "":
        return "subject and body must be separated by exactly one blank line"

    body = lines[2:]
    if not body:
        return "commit body is required"
    if any(not line.strip() for line in body):
        return "commit body must not contain blank lines"
    if any(line != line.rstrip() for line in body):
        return "commit body must not contain trailing whitespace"
    if any(not line.startswith("- ") or not line[2:].strip() for line in body):
        return "commit body must use consecutive '- ' bullets"
    return None


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: check_commit_message.py COMMIT_MESSAGE_FILE", file=sys.stderr)
        return 2
    try:
        text = Path(arguments[0]).read_text(encoding="utf-8")
    except OSError as error:
        print(f"cannot read commit message: {error}", file=sys.stderr)
        return 2
    error = validate_message(text)
    if error:
        print(f"invalid commit message: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
