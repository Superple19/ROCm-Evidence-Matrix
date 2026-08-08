import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .history import update_execution_evidence
from .validation import validate_runtime_verifications


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def environment_evidence():
    return {name: os.environ[name] for name in ("ROCM_PATH", "HIP_PATH", "HSA_OVERRIDE_GFX_VERSION") if os.environ.get(name)}


def collect_runtime(torch_module, observed_at=None, candidate_id=None, gfx=None):
    observed_at = observed_at or utc_now()
    record = {
        "id": f"runtime:{candidate_id or 'unlinked'}:{observed_at}",
        "candidate_id": candidate_id,
        "gfx": gfx,
        "observed_at": observed_at,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "os": sys.platform,
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
        "driver_version": os.environ.get("AMDGPU_DRIVER_VERSION") or os.environ.get("ROCM_DRIVER_VERSION"),
        "environment": environment_evidence(),
        "torch_version": getattr(torch_module, "__version__", None),
        "hip_version": getattr(getattr(torch_module, "version", None), "hip", None),
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
                record["devices"].append(device)
        record["result"] = "passed" if record["rocm_available"] and record["device_count"] > 0 else "failed"
        if record["result"] == "failed":
            record["error"] = "ROCm device enumeration returned no available device"
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
    return record


def merge_runtime(existing, record):
    records = list((existing or {}).get("verifications", []))
    records.append(record)
    return {"schema_version": 1, "generated_at": record["observed_at"], "verifications": records}


def write_runtime(record, output_path):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_runtime(existing, record)
    validate_runtime_verifications(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Record ROCm runtime evidence from the current Python environment.")
    parser.add_argument("--output", default="data/verifications/runtime.json")
    parser.add_argument("--candidate-id")
    parser.add_argument("--gfx")
    parser.add_argument("--history", default="data/history.json")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        import torch
    except ImportError as error:
        raise SystemExit(f"PyTorch is not installed: {error}") from error
    record = collect_runtime(torch, candidate_id=args.candidate_id, gfx=args.gfx)
    write_runtime(record, args.output)
    if args.candidate_id:
        update_execution_evidence(args.history, "runtime", args.candidate_id, record["result"])
    print(f"Runtime verification {record['result']}; wrote {args.output}")
    if record["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
