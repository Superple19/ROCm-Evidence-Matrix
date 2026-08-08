import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .validation import validate_community_evidence


SENSITIVE_KEYS = {"username", "user", "hostname", "computer_name", "cwd", "home", "home_dir", "path", "command_path"}
WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s]+")
POSIX_PATH = re.compile(r"/(?:home|Users|mnt|workspace)/[^\s]+")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redact(value, key=None):
    if key in SENSITIVE_KEYS:
        return "<redacted>"
    if isinstance(value, dict):
        return {name: _redact(item, name) for name, item in value.items() if name not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return POSIX_PATH.sub("<redacted>", WINDOWS_PATH.sub("<redacted>", value))
    return value


def submission_from_record(record, evidence_kind, submitted_at=None):
    if evidence_kind not in {"runtime", "hardware"}:
        raise ValueError("Community evidence kind must be runtime or hardware")
    submitted_at = submitted_at or utc_now()
    clean = _redact(copy.deepcopy(record))
    payload = {"evidence_kind": evidence_kind, "observed_at": clean.get("observed_at"), "result": clean.get("result"), "record": clean}
    content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "id": f"community:{evidence_kind}:{content_hash[:16]}",
        "content_hash": content_hash,
        "evidence_kind": evidence_kind,
        "source": "community",
        "provenance": "self-reported",
        "observed_at": clean.get("observed_at") or submitted_at,
        "submitted_at": submitted_at,
        "result": clean.get("result", "failed"),
        "record": clean,
        "privacy_redacted": True,
    }


def merge_submission(existing, submission):
    existing = existing or {"schema_version": 1, "generated_at": submission["submitted_at"], "submissions": []}
    submissions = list(existing.get("submissions", []))
    if not any(item.get("content_hash") == submission["content_hash"] for item in submissions):
        submissions.append(submission)
    document = {"schema_version": 1, "generated_at": submission["submitted_at"], "submissions": submissions}
    validate_community_evidence(document)
    return document


def write_submission(record, evidence_kind, output_path, submitted_at=None):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_submission(existing, submission_from_record(record, evidence_kind, submitted_at))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return document


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare privacy-redacted community ROCm evidence for review.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--kind", choices=("runtime", "hardware"), required=True)
    parser.add_argument("--output", default="contributions/community-evidence.json")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    record = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if "verifications" in record:
        record = record["verifications"][-1]
    document = write_submission(record, args.kind, args.output)
    print(f"Prepared {len(document['submissions'])} community submission(s) in {args.output}")


if __name__ == "__main__":
    main()
