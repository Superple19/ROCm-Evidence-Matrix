import argparse
from importlib import metadata
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

from .identity import candidate_hash, default_platform_tag, python_tag, rocm_version_from_torch
from .history import execution_evidence_errors
from .persistence import atomic_write_json
from .source_adapter import monotonic_generated_at
from .validation import validate_runtime_verifications


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def environment_evidence():
    return {name: os.environ[name] for name in ("ROCM_PATH", "HIP_PATH", "HSA_OVERRIDE_GFX_VERSION") if os.environ.get(name)}


def installed_package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def normalized_os():
    return {
        "windows": "windows",
        "linux": "linux",
        "darwin": "macos",
    }.get(platform.system().lower(), "unknown")


def collect_runtime(torch_module, observed_at=None, candidate_id=None, gfx=None):
    observed_at = observed_at or utc_now()
    record = {
        "id": f"runtime:{candidate_id or 'unlinked'}:{observed_at}",
        "candidate_id": candidate_id,
        "gfx": gfx,
        "observed_at": observed_at,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "os": normalized_os(),
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
        "driver_version": os.environ.get("AMDGPU_DRIVER_VERSION") or os.environ.get("ROCM_DRIVER_VERSION"),
        "environment": environment_evidence(),
        "torch_version": getattr(torch_module, "__version__", None),
        "torchvision_version": installed_package_version("torchvision"),
        "torchaudio_version": installed_package_version("torchaudio"),
        "hip_version": getattr(getattr(torch_module, "version", None), "hip", None),
        "rocm_version": rocm_version_from_torch(getattr(torch_module, "__version__", None)),
        "python_tag": python_tag(),
        "platform_tag": None,
        "candidate_hash": None,
        "rocm_available": False,
        "device_count": 0,
        "devices": [],
        "result": "failed",
        "error": None,
    }
    try:
        cuda = torch_module.cuda
        record["rocm_available"] = bool(cuda.is_available())
        if record["rocm_available"]:
            record["device_count"] = int(cuda.device_count())
            for index in range(record["device_count"]):
                properties = cuda.get_device_properties(index)
                device = {"index": index, "name": str(properties.name)}
                for field in ("gcnArchName", "multi_processor_count", "total_memory"):
                    value = getattr(properties, field, None)
                    if value is not None:
                        device[field] = str(value) if field == "gcnArchName" else int(value)
                if "gcnArchName" in device:
                    device["gfx"] = device["gcnArchName"]
                    if record["gfx"] is None:
                        record["gfx"] = device["gfx"]
                record["devices"].append(device)
        record["result"] = "passed" if record["rocm_available"] and record["device_count"] > 0 else "failed"
        if record["result"] == "failed":
            record["error"] = "ROCm device enumeration returned no available device"
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
    return record


def merge_runtime(existing, record):
    records = list((existing or {}).get("verifications", []))
    known = {item.get("id") for item in records}
    if record.get("id") not in known:
        records.append(record)
    return {
        "schema_version": 1,
        "generated_at": monotonic_generated_at(existing, record["observed_at"]),
        "verifications": records,
    }
    record["evidence_id"] = record["id"]


def write_runtime(record, output_path):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_runtime(existing, record)
    validate_runtime_verifications(document)
    atomic_write_json(document, path)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Record ROCm runtime evidence from the current Python environment.")
    parser.add_argument("--output", default="data/verifications/runtime.json")
    parser.add_argument("--candidate-id")
    parser.add_argument("--gfx")
    parser.add_argument(
        "--history",
        default="data/history.json",
        help="Read-only candidate reference; runtime never updates this file",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        import torch
    except ImportError as error:
        raise SystemExit(f"PyTorch is not installed: {error}") from error
    record = collect_runtime(torch, candidate_id=args.candidate_id, gfx=args.gfx)
    candidate_errors = []
    if args.candidate_id:
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))
        candidate = next((item for item in history.get("candidates", []) if item.get("id") == args.candidate_id), None)
        if candidate is not None:
            record["platform_tag"] = default_platform_tag(candidate)
            record["candidate_hash"] = candidate_hash(candidate, record.get("gfx"), record["python_tag"], record["platform_tag"])
            candidate_errors = execution_evidence_errors(candidate, record, "runtime", args.gfx)
        else:
            candidate_errors = [f"unknown candidate: {args.candidate_id}"]
        record["candidate_match"] = not candidate_errors
        record["candidate_errors"] = candidate_errors or None
    write_runtime(record, args.output)
    if candidate_errors:
        raise SystemExit("Runtime evidence did not match the selected candidate: " + "; ".join(candidate_errors))
    print(f"Runtime verification {record['result']}; wrote {args.output}")
    if record["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
