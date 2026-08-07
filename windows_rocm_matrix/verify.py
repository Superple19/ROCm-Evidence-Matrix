import argparse
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import venv
from datetime import datetime, timezone
from pathlib import Path

from .resolve import install_arguments, resolve_candidates
from .validation import validate_resolver_verifications


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


def install_arguments_for_candidate(candidate, gfx):
    if candidate.get("distribution_family", "therock") == "therock":
        return install_arguments(candidate, gfx)
    urls = candidate.get("wheel_urls")
    if not urls:
        raise ValueError("Legacy resolver candidates must provide direct wheel_urls")
    return ["install", "--no-index", *urls]


def candidate_hash(candidate, gfx, python_tag, platform_tag=None):
    identity = {
        "distribution_family": candidate.get("distribution_family", "therock"),
        "source_id": candidate.get("source_id"),
        "gfx": gfx,
        "python_tag": python_tag,
        "platform_tag": platform_tag,
        "packages": {name: candidate.get(name) for name in ("rocm_version", "torch_version", "torchvision_version", "torchaudio_version")},
        "wheel_urls": candidate.get("wheel_urls", []),
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
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-20:]) or None


def merge_verification(existing, observation):
    records = list((existing or {}).get("verifications", []))
    if not any(item.get("id") == observation.get("id") for item in records):
        records.append(observation)
    return {
        "schema_version": 1,
        "generated_at": observation["observed_at"],
        "verifications": sorted(records, key=lambda item: (item["observed_at"], item["id"])),
    }


def verify_candidate(candidate, gfx, timeout, python_tag=None, platform_tag=None):
    observed_at = utc_now()
    python_tag = python_tag or current_python_tag()
    record = {
        "id": f"{candidate['id']}:{gfx or 'unknown'}:{python_tag}:{platform_tag or sysconfig.get_platform()}",
        "candidate_hash": candidate_hash(candidate, gfx, python_tag, platform_tag),
        "candidate_id": candidate["id"],
        "distribution_family": candidate.get("distribution_family", "therock"),
        "source_id": candidate["source_id"],
        "gfx": gfx,
        "platform": candidate.get("platform", "windows"),
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
        venv.EnvBuilder(with_pip=True).create(root)
        python = root / "Scripts" / "python.exe"
        pip_version = subprocess.run(
            [python, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()[1]
        record["pip_version"] = pip_version
        report_path = root / "report.json"
        try:
            environment = {**os.environ, "PIP_CACHE_DIR": str(root / "pip-cache")}
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
            output = (error.stdout or "") + "\n" + (error.stderr or "")
            record["error"] = error_summary(output) or f"Resolver timed out after {timeout} seconds"
    return record


def write_verification(record, output_path):
    path = Path(output_path)
    existing = None
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    document = merge_verification(existing, record)
    validate_resolver_verifications(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verify one ROCm package candidate with pip in a disposable environment.")
    parser.add_argument("--history", default="data/history.json")
    parser.add_argument("--output", default="data/verifications/resolver.json")
    parser.add_argument("--gfx")
    parser.add_argument("--platform", choices=("windows", "linux", "macos", "unknown"))
    parser.add_argument("--python", dest="python_tag")
    parser.add_argument("--platform-tag")
    parser.add_argument("--channel", choices=("stable", "nightly", "staging"))
    parser.add_argument("--rocm")
    parser.add_argument("--torch")
    parser.add_argument("--timeout", type=int, default=900)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    python_tag = args.python_tag or current_python_tag()
    matches = resolve_candidates(
        history,
        args.gfx,
        platform=args.platform,
        channel=args.channel,
        rocm_version=args.rocm,
        torch_series=args.torch,
        python_tag=python_tag,
    )
    if not matches:
        raise SystemExit(f"No available candidate matches {args.gfx} and the current interpreter ({python_tag})")
    candidate = matches[0]
    print(f"Verifying {candidate['id']} for {args.gfx} and {python_tag}")
    record = verify_candidate(candidate, args.gfx, args.timeout, python_tag, args.platform_tag)
    write_verification(record, args.output)
    print(f"Resolver verification {record['result']}; wrote {args.output}")
    if record["result"] != "passed":
        if record["error"]:
            print(record["error"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
