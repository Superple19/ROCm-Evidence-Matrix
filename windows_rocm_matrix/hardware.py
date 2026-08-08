import argparse
import json
import os
import platform
import time
from pathlib import Path

from .runtime import environment_evidence, normalized_os, utc_now
from .history import update_execution_evidence
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
        "hip_version": getattr(getattr(torch_module, "version", None), "hip", None),
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
    records.append(record)
    return {"schema_version": 1, "generated_at": record["observed_at"], "verifications": records}


def write_hardware(record, output_path):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_hardware(existing, record)
    validate_hardware_verifications(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run a reproducible ROCm GPU tensor smoke test.")
    parser.add_argument("--output", default="data/verifications/hardware.json")
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
    record = collect_hardware(torch, candidate_id=args.candidate_id, gfx=args.gfx)
    write_hardware(record, args.output)
    if args.candidate_id:
        update_execution_evidence(args.history, "hardware", args.candidate_id, record["result"])
    print(f"Hardware verification {record['result']}; wrote {args.output}")
    if record["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
