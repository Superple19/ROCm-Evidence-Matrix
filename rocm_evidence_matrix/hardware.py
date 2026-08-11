import argparse
import json
import os
import platform
import time
from pathlib import Path

from .identity import candidate_hash, default_platform_tag, python_tag, rocm_version_from_torch
from .runtime import environment_evidence, installed_package_version, normalized_os, utc_now
from .history import execution_evidence_errors
from .persistence import atomic_write_json
from .source_adapter import monotonic_generated_at
from .validation import validate_hardware_verifications


def collect_hardware(torch_module, observed_at=None, candidate_id=None, gfx=None):
    observed_at = observed_at or utc_now()
    record = {
        "id": f"hardware:{candidate_id or 'unlinked'}:{observed_at}",
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
        "operation": "2x2 float32 GPU matmul with synchronization",
        "command": "torch.ones((2, 2), device='cuda') @ torch.ones((2, 2), device='cuda'); torch.cuda.synchronize()",
        "device": None,
        "elapsed_ms": None,
        "result": "failed",
        "correct": False,
        "error": None,
    }
    try:
        cuda = torch_module.cuda
        if not cuda.is_available() or cuda.device_count() < 1:
            raise RuntimeError("ROCm device enumeration returned no available device")
        properties = cuda.get_device_properties(0)
        record["device"] = {"index": 0, "name": str(properties.name)}
        arch = getattr(properties, "gcnArchName", None)
        if arch is not None:
            record["device"]["gcnArchName"] = str(arch)
            record["device"]["gfx"] = str(arch)
            if record["gfx"] is None:
                record["gfx"] = record["device"]["gfx"]
        started = time.perf_counter()
        left = torch_module.ones((2, 2), device="cuda", dtype=torch_module.float32)
        right = torch_module.ones((2, 2), device="cuda", dtype=torch_module.float32)
        result = left @ right
        cuda.synchronize()
        record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        record["correct"] = bool(torch_module.allclose(result, torch_module.full((2, 2), 2, device="cuda", dtype=torch_module.float32)))
        record["result"] = "passed" if record["correct"] else "failed"
        if not record["correct"]:
            record["error"] = "GPU matrix result did not match the expected tensor"
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
    return record


def merge_hardware(existing, record):
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


def write_hardware(record, output_path):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_hardware(existing, record)
    validate_hardware_verifications(document)
    atomic_write_json(document, path)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run a reproducible ROCm GPU tensor smoke test.")
    parser.add_argument("--output", default="data/verifications/hardware.json")
    parser.add_argument("--candidate-id")
    parser.add_argument("--gfx")
    parser.add_argument(
        "--history",
        default="data/history.json",
        help="Read-only candidate reference; hardware never updates this file",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        import torch
    except ImportError as error:
        raise SystemExit(f"PyTorch is not installed: {error}") from error
    record = collect_hardware(torch, candidate_id=args.candidate_id, gfx=args.gfx)
    candidate_errors = []
    if args.candidate_id:
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))
        candidate = next((item for item in history.get("candidates", []) if item.get("id") == args.candidate_id), None)
        if candidate is not None:
            record["platform_tag"] = default_platform_tag(candidate)
            record["candidate_hash"] = candidate_hash(candidate, record.get("gfx"), record["python_tag"], record["platform_tag"])
            candidate_errors = execution_evidence_errors(candidate, record, "hardware", args.gfx)
        else:
            candidate_errors = [f"unknown candidate: {args.candidate_id}"]
        record["candidate_match"] = not candidate_errors
        record["candidate_errors"] = candidate_errors or None
    write_hardware(record, args.output)
    if candidate_errors:
        raise SystemExit("Hardware evidence did not match the selected candidate: " + "; ".join(candidate_errors))
    print(f"Hardware verification {record['result']}; wrote {args.output}")
    if record["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
