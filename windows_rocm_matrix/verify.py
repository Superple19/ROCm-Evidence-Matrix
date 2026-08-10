import argparse
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import venv
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .resolve import host_platform, install_arguments, resolve_candidates
from .source_adapter import monotonic_generated_at
from .validation import validate_history, validate_resolver_verifications


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def current_python_tag():
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def verification_arguments(candidate, gfx, report_path, python_tag=None, platform_tag=None):
    install = install_arguments_for_candidate(candidate, gfx)
    arguments = [
        install[0],
        "--dry-run",
        "--ignore-installed",
        "--disable-pip-version-check",
        "--no-input",
        "--report",
        str(report_path),
        *install[1:],
    ]
    if platform_tag:
        arguments[1:1] = ["--platform", platform_tag, "--only-binary=:all:"]
    if python_tag and platform_tag:
        arguments[1:1] = ["--python-version", python_tag.removeprefix("cp"), "--implementation", "cp", "--abi", python_tag]
    return arguments


def normalized_command(candidate, gfx, python_tag=None, platform_tag=None):
    return ["python", "-m", "pip", *verification_arguments(candidate, gfx, "<report.json>", python_tag, platform_tag)]


def default_platform_tag(candidate):
    if candidate.get("distribution_family") == "legacy" and candidate.get("platform") == "linux":
        urls = candidate.get("wheel_urls", [])
        if any("linux_x86_64" in url for url in urls):
            return "linux_x86_64"
    return {
        "linux": "manylinux_2_28_x86_64",
        "windows": "win_amd64",
        "macos": "macosx_11_0_x86_64",
    }.get(candidate.get("platform", "windows"))


def install_arguments_for_candidate(candidate, gfx):
    if candidate.get("distribution_family", "therock") == "therock":
        return install_arguments(candidate, gfx)
    urls = candidate.get("wheel_urls")
    if not urls:
        raise ValueError("Legacy resolver candidates must provide direct wheel_urls")
    return ["install", "--index-url", "https://pypi.org/simple", *urls]


def candidate_hash(candidate, gfx, python_tag, platform_tag=None):
    identity = {
        "distribution_family": candidate.get("distribution_family", "therock"),
        "source_id": candidate.get("source_id"),
        "gfx": gfx,
        "python_tag": python_tag,
        "platform_tag": platform_tag,
        "packages": {name: candidate.get(name) for name in ("rocm_version", "torch_version", "torchvision_version", "torchaudio_version")},
        "wheel_urls": sorted(candidate.get("wheel_urls", [])),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()


def resolved_packages(report):
    packages = []
    for item in report.get("install", []):
        metadata = item.get("metadata", {})
        download = item.get("download_info", {})
        archive = download.get("archive_info", {})
        hashes = archive.get("hashes", {})
        packages.append(
            {
                "name": metadata.get("name", ""),
                "version": metadata.get("version", ""),
                "url": download.get("url", ""),
                "sha256": hashes.get("sha256"),
            }
        )
    return sorted(packages, key=lambda item: (item["name"].lower(), item["version"]))


def error_summary(output):
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-20:]) or None


def combined_process_output(*values):
    return "\n".join(
        value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        for value in values
    )


def virtualenv_python(root, host_os=None):
    """Return the interpreter path created by venv on the current host."""
    host_os = host_os or os.name
    relative = Path("Scripts") / "python.exe" if host_os == "nt" else Path("bin") / "python"
    return Path(root) / relative


def create_disposable_environment(root):
    try:
        import ensurepip
    except ModuleNotFoundError:
        subprocess.run([sys.executable, "-m", "virtualenv", str(root)], check=True, capture_output=True, text=True)
        return
    try:
        venv.EnvBuilder(with_pip=True).create(root)
    except (OSError, RuntimeError, subprocess.CalledProcessError, SystemExit) as error:
        try:
            subprocess.run([sys.executable, "-m", "virtualenv", str(root)], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as fallback_error:
            raise error from fallback_error


def merge_verification(existing, observation):
    return merge_verification_batch(existing, [observation])


def merge_verification_batch(existing, observations):
    records = list((existing or {}).get("verifications", []))
    known = {item.get("id") for item in records}
    for observation in observations:
        if observation.get("id") not in known:
            records.append(observation)
            known.add(observation.get("id"))
    generated_at = (existing or {}).get("generated_at") or utc_now()
    if observations:
        generated_at = monotonic_generated_at(existing, max(item["observed_at"] for item in observations))
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "verifications": sorted(records, key=lambda item: (item["observed_at"], item["id"])),
    }


def read_verification_log(log_path):
    path = Path(log_path)
    if not path.exists():
        return []
    records = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                if index != len(lines) - 1:
                    raise
    return records


def append_verification_log(record, log_path):
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def write_json_document(document, path, validator):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    validator(document)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_history_document(history, history_path):
    write_json_document(history, history_path, validate_history)


def apply_history_evidence(
    history,
    candidate_id,
    result,
    gfx=None,
    python_tag=None,
    platform_tag=None,
    verification_id=None,
    observed_at=None,
    error=None,
    host_platform_name=None,
    command=None,
    exit_code=None,
):
    if result not in {"passed", "failed", "not_applicable"}:
        raise ValueError(f"Invalid resolver result: {result}")
    if not verification_id:
        raise ValueError("Resolver evidence requires a verification ID")
    for candidate in history.get("candidates", []):
        if candidate.get("id") != candidate_id:
            continue
        evidence = candidate.setdefault("evidence_status", {"artifact": "artifact_available", "documentation": "not_collected", "ci": "not_collected", "resolver": "not_collected", "runtime": "not_collected", "hardware": "not_collected"})
        results = candidate.setdefault("resolver_results", [])
        observed_at = observed_at or utc_now()
        if any(item.get("verification_id") == verification_id for item in results):
            return True
        results.append(
            {
                "candidate_id": candidate_id,
                "candidate_hash": candidate_hash(candidate, gfx, python_tag, platform_tag),
                "distribution_family": candidate.get("distribution_family", "therock"),
                "platform": candidate.get("platform", "unknown"),
                "host_platform": host_platform_name,
                "gfx": gfx,
                "python_tag": python_tag,
                "platform_tag": platform_tag,
                "command": command,
                "exit_code": exit_code,
                "result": result,
                "verification_id": verification_id,
                "observed_at": observed_at,
                "error": error,
                "snapshot_observed_at": candidate.get("last_observed_at"),
            }
        )
        passed = [item for item in results if item.get("result") == "passed"]
        failed = [item for item in results if item.get("result") == "failed"]
        not_applicable = [item for item in results if item.get("result") == "not_applicable"]
        evidence["resolver"] = "partial" if passed and (failed or not_applicable) else "resolver_verified" if passed else "resolver_failed" if failed else "not_applicable"
        validate_history(history)
        return True
    return False


def verify_candidate(candidate, gfx, timeout, python_tag=None, platform_tag=None, cache_dir=None):
    observed_at = utc_now()
    attempt_id = uuid.uuid4().hex[:12]
    python_tag = python_tag or current_python_tag()
    platform_tag = platform_tag or default_platform_tag(candidate)
    record = {
        "id": f"{candidate['id']}:{gfx or 'unknown'}:{python_tag}:{platform_tag or sysconfig.get_platform()}:{observed_at}:{attempt_id}",
        "candidate_hash": candidate_hash(candidate, gfx, python_tag, platform_tag),
        "candidate_id": candidate["id"],
        "distribution_family": candidate.get("distribution_family", "therock"),
        "source_id": candidate["source_id"],
        "gfx": gfx,
        "platform": candidate.get("platform", "windows"),
        "host_platform": host_platform(),
        "python_tag": python_tag,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "platform_tag": platform_tag or sysconfig.get_platform().replace("-", "_").replace(".", "_"),
        "packages": {
            "torch": candidate["torch_version"],
            "torchvision": candidate["torchvision_version"],
            "torchaudio": candidate["torchaudio_version"],
        },
        "command": normalized_command(candidate, gfx, python_tag, platform_tag),
        "observed_at": observed_at,
        "result": "failed",
        "exit_code": None,
        "pip_version": None,
        "resolved_packages": [],
        "error": None,
    }
    with tempfile.TemporaryDirectory(prefix="windows-rocm-verify-") as directory:
        root = Path(directory)
        create_disposable_environment(root)
        python = virtualenv_python(root)
        pip_version = subprocess.run(
            [python, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()[1]
        record["pip_version"] = pip_version
        report_path = root / "report.json"
        try:
            pip_cache = Path(cache_dir) if cache_dir else root / "pip-cache"
            pip_cache.mkdir(parents=True, exist_ok=True)
            environment = {**os.environ, "PIP_CACHE_DIR": str(pip_cache)}
            completed = subprocess.run(
                [python, "-m", "pip", *verification_arguments(candidate, gfx, report_path, python_tag, platform_tag)],
                capture_output=True,
                env=environment,
                text=True,
                timeout=timeout,
            )
            record["exit_code"] = completed.returncode
            if completed.returncode == 0 and report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                record["resolved_packages"] = resolved_packages(report)
                record["result"] = "passed"
            else:
                record["error"] = error_summary(completed.stdout + "\n" + completed.stderr)
        except subprocess.TimeoutExpired as error:
            output = combined_process_output(error.stdout, error.stderr)
            record["error"] = error_summary(output) or f"Resolver timed out after {timeout} seconds"
    return record


def write_verification(record, output_path):
    path = Path(output_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    document = merge_verification(existing, record)
    write_json_document(document, path, validate_resolver_verifications)


def update_history_evidence(
    history_path,
    candidate_id,
    result,
    gfx=None,
    python_tag=None,
    platform_tag=None,
    verification_id=None,
    observed_at=None,
    error=None,
    host_platform_name=None,
    command=None,
    exit_code=None,
):
    path = Path(history_path)
    history = json.loads(path.read_text(encoding="utf-8"))
    updated = apply_history_evidence(
        history,
        candidate_id,
        result,
        gfx,
        python_tag,
        platform_tag,
        verification_id,
        observed_at,
        error,
        host_platform_name,
        command,
        exit_code,
    )
    if updated:
        write_history_document(history, path)
    return updated


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verify one ROCm package candidate with pip in a disposable environment.")
    parser.add_argument("--history", default="data/history.json")
    parser.add_argument("--output", default="data/verifications/resolver.json")
    parser.add_argument("--gfx")
    parser.add_argument("--platform", choices=("windows", "linux", "macos", "unknown"))
    parser.add_argument("--distribution-family", choices=("therock", "legacy"))
    parser.add_argument("--python", dest="python_tag")
    parser.add_argument("--platform-tag")
    parser.add_argument("--channel", choices=("stable", "nightly", "staging"))
    parser.add_argument("--rocm")
    parser.add_argument("--torch")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--include-failed", action="store_true", help="Allow candidates with previous resolver failures to be retried.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    python_tag = args.python_tag or current_python_tag()
    platform = args.platform or host_platform()
    matches = resolve_candidates(
        history,
        args.gfx,
        platform=platform,
        channel=args.channel,
        rocm_version=args.rocm,
        torch_series=args.torch,
        python_tag=python_tag,
        include_failed=args.include_failed,
    )
    if args.distribution_family:
        matches = [candidate for candidate in matches if candidate.get("distribution_family") == args.distribution_family]
    if not matches:
        raise SystemExit(f"No available candidate matches {args.gfx} and the current interpreter ({python_tag})")
    candidate = matches[0]
    print(f"Verifying {candidate['id']} for {args.gfx} and {python_tag}")
    record = verify_candidate(candidate, args.gfx, args.timeout, python_tag, args.platform_tag)
    write_verification(record, args.output)
    update_history_evidence(
        args.history,
        candidate["id"],
        record["result"],
        args.gfx,
        python_tag,
        record["platform_tag"],
        record["id"],
        record["observed_at"],
        record.get("error"),
        record.get("host_platform"),
        record.get("command"),
        record.get("exit_code"),
    )
    print(f"Resolver verification {record['result']}; wrote {args.output}")
    if record["result"] != "passed":
        if record["error"]:
            print(record["error"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
