import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .persistence import atomic_write_json
from .source_adapter import monotonic_generated_at
from .validation import validate_community_evidence


SENSITIVE_KEYS = {"username", "user", "hostname", "computer_name", "cwd", "home", "home_dir", "path", "command_path"}
WINDOWS_PATH = re.compile(r"[A-Za-z]:\\(?:[^\\\"']+\\?)*[^\s\"']*")
POSIX_PATH = re.compile(r"/(?:home|Users|mnt|workspace|workspaces|tmp|opt|var|root|data|usr|etc|run|projects|repos|srv|app)/[^\s\"']+")
SECRET_VALUE = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:token|api[_-]?token|secret|password|authorization|api[_-]?key)\b\s*[:=]\s*(?:bearer\s+)?[^,;\s]+")

COMMON_RECORD_FIELDS = {
    "id", "candidate_id", "candidate_hash", "gfx", "observed_at", "python_version", "python_tag", "os", "platform", "platform_tag", "architecture",
    "driver_version", "torch_version", "rocm_version", "hip_version", "result", "error",
}
RUNTIME_RECORD_FIELDS = COMMON_RECORD_FIELDS | {"rocm_available", "device_count", "devices"}
HARDWARE_RECORD_FIELDS = COMMON_RECORD_FIELDS | {"device", "elapsed_ms", "correct", "operation"}
DEVICE_FIELDS = {"index", "name", "gcnArchName", "gfx", "multi_processor_count", "total_memory"}


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
        value = SECRET_VALUE.sub("<redacted-secret>", value)
        return POSIX_PATH.sub("<redacted>", WINDOWS_PATH.sub("<redacted>", value))
    return value


def _allowed_record(record, evidence_kind):
    fields = RUNTIME_RECORD_FIELDS if evidence_kind == "runtime" else HARDWARE_RECORD_FIELDS
    clean = {name: record[name] for name in fields if name in record}
    if "devices" in clean:
        clean["devices"] = [
            {name: _redact(value, name) for name, value in device.items() if name in DEVICE_FIELDS}
            for device in clean["devices"]
            if isinstance(device, dict)
        ]
    if "device" in clean and isinstance(clean["device"], dict):
        clean["device"] = {name: _redact(value, name) for name, value in clean["device"].items() if name in DEVICE_FIELDS}
    return _redact(clean)


def submission_from_record(record, evidence_kind, submitted_at=None):
    if evidence_kind not in {"runtime", "hardware"}:
        raise ValueError("Community evidence kind must be runtime or hardware")
    submitted_at = submitted_at or utc_now()
    if not isinstance(record, dict):
        raise ValueError("Community evidence record must be an object")
    clean = _allowed_record(copy.deepcopy(record), evidence_kind)
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
    document = {
        "schema_version": 1,
        "generated_at": monotonic_generated_at(existing, submission["submitted_at"]),
        "submissions": submissions,
    }
    validate_community_evidence(document)
    return document


def write_submission(record, evidence_kind, output_path, submitted_at=None):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_submission(existing, submission_from_record(record, evidence_kind, submitted_at))
    atomic_write_json(document, path)
    return document


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare a privacy-redacted local ROCm diagnostic report.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--kind", choices=("runtime", "hardware"), required=True)
    parser.add_argument("--output", default="data/verifications/local-evidence.json")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    record = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if "verifications" in record:
        record = record["verifications"][-1]
    document = write_submission(record, args.kind, args.output)
    print(f"Prepared {len(document['submissions'])} local diagnostic record(s) in {args.output}")


if __name__ == "__main__":
    main()
