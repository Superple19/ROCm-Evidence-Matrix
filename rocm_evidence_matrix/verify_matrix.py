"""Run resolver dry-runs for a platform/channel/GFX/Python matrix."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import threading

from .resolve import host_platform, resolve_candidates
from .validation import validate_resolver_verifications
from .verify import (
    append_verification_log,
    apply_history_evidence,
    candidate_hash,
    default_platform_tag,
    merge_verification_batch,
    read_verification_log,
    verify_candidate,
    write_history_document,
    write_json_document,
)


PREFERRED_GFX = ("gfx1201", "gfx1100", "gfx1030", "gfx90a")
DEFAULT_CHANNELS = ("stable", "nightly", "staging")


def default_cache_dir():
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return str(Path(root) / "rocm-matrix" / "pip")
    return str(Path.home() / ".cache" / "rocm-matrix" / "pip")


def evidence_log_path(output_path):
    return Path(output_path).with_suffix(".jsonl")


def platform_tag_for(platform, requested=None, candidate=None):
    if requested:
        return requested
    if candidate is not None:
        return default_platform_tag(candidate)
    return {
        "linux": "manylinux_2_28_x86_64",
        "windows": "win_amd64",
        "macos": "macosx_11_0_x86_64",
    }.get(platform)


def representative_targets(candidates, all_gfx=False):
    targets = sorted({target for candidate in candidates for target in candidate.get("available_gfx_targets", [])}, reverse=True)
    if all_gfx:
        return targets
    preferred = [target for target in PREFERRED_GFX if target in targets]
    return preferred or targets[:1]


def matrix_jobs(history, platform, channels, gfx=None, python_tag=None, limit=None, platform_tag=None, distribution_family=None, rocm_version=None, torch_series=None, all_candidates=False, all_gfx=False):
    jobs = []
    seen = set()

    def add_job(candidate, target, tag):
        job = (candidate, target, tag, platform_tag_for(platform, platform_tag, candidate))
        key = matrix_job_key(job)
        if key in seen:
            return False
        seen.add(key)
        jobs.append(job)
        return limit is not None and len(jobs) >= limit

    for channel in channels:
        candidates = resolve_candidates(history, None, platform=platform, channel=channel, rocm_version=rocm_version, torch_series=torch_series, python_tag=python_tag, include_failed=True)
        candidates = [candidate for candidate in candidates if not distribution_family or candidate.get("distribution_family") == distribution_family]
        if not candidates:
            continue
        if not all_candidates:
            targets = [gfx] if gfx else representative_targets(candidates, all_gfx)
            for target in targets:
                matching = [candidate for candidate in candidates if target in candidate.get("available_gfx_targets", [])]
                for candidate in matching[:1]:
                    python_tags = [python_tag] if python_tag else candidate["python_tags"]
                    for tag in python_tags:
                        if add_job(candidate, target, tag):
                            return jobs
            legacy_without_gfx = [candidate for candidate in candidates if candidate.get("distribution_family") == "legacy" and platform == "linux" and not candidate.get("available_gfx_targets")]
            if not gfx and legacy_without_gfx:
                candidate = legacy_without_gfx[0]
                python_tags = [python_tag] if python_tag else candidate["python_tags"]
                for tag in python_tags:
                    if add_job(candidate, None, tag):
                        return jobs
            continue
        for candidate in candidates:
            if distribution_family and candidate.get("distribution_family") != distribution_family:
                continue
            if candidate.get("distribution_family") == "legacy" and platform == "linux" and not candidate.get("available_gfx_targets"):
                python_tags = [python_tag] if python_tag else candidate["python_tags"]
                for tag in python_tags:
                    if add_job(candidate, None, tag):
                        return jobs
                continue
            targets = candidate.get("available_gfx_targets", [])
            if not targets:
                continue
            selected_targets = [gfx] if gfx else targets
            for target in selected_targets:
                if target not in targets:
                    continue
                python_tags = [python_tag] if python_tag else candidate["python_tags"]
                for tag in python_tags:
                    if add_job(candidate, target, tag):
                        return jobs
    return jobs


def matrix_exit_code(records):
    return 1 if any(record.get("result") == "failed" for record in records) else 0


def matrix_job_key(job):
    candidate, gfx, python_tag, platform_tag = job
    return candidate_hash(candidate, gfx, python_tag, platform_tag), gfx, python_tag, platform_tag


def completed_job_keys(output_path, history=None, evidence_log=None):
    records = []
    path = Path(output_path)
    if path.exists():
        records.extend(json.loads(path.read_text(encoding="utf-8")).get("verifications", []))
    log_path = Path(evidence_log) if evidence_log else evidence_log_path(path)
    records.extend(read_verification_log(log_path))
    if history:
        for candidate in history.get("candidates", []):
            records.extend(candidate.get("resolver_results", []))
    return {
        (record.get("candidate_hash"), record.get("gfx"), record.get("python_tag"), record.get("platform_tag"))
        for record in records
        if record.get("candidate_hash")
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verify ROCm package candidates across a platform matrix.")
    parser.add_argument("--history", default="data/history.json")
    parser.add_argument("--output", default="data/verifications/resolver.json")
    parser.add_argument("--platform", choices=("linux", "windows", "macos"), default=host_platform())
    parser.add_argument("--distribution-family", choices=("therock", "legacy"))
    parser.add_argument("--channel", action="append", dest="channels", choices=("stable", "nightly", "staging"))
    parser.add_argument("--gfx", action="append")
    parser.add_argument("--python", dest="python_tag")
    parser.add_argument("--rocm")
    parser.add_argument("--torch")
    parser.add_argument("--platform-tag")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--cache-dir", default=default_cache_dir(), help="Persistent pip cache on the host filesystem; disposable environments remain isolated.")
    parser.add_argument("--evidence-log", help="Append-only JSONL evidence log (defaults beside the resolver output).")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent resolver subprocesses (default: 1).")
    parser.add_argument("--all-candidates", action="store_true", help="Verify every matching candidate instead of one representative candidate per channel and target.")
    parser.add_argument("--all-gfx", action="store_true", help="Verify every available GFX target instead of representative targets.")
    parser.add_argument("--exhaustive", action="store_true", help="Explicitly allow --all-candidates and --all-gfx historical matrix runs.")
    parser.add_argument("--resume", action="store_true", help="Skip candidate/GFX/Python combinations already present in the output evidence.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if (args.all_candidates or args.all_gfx) and not args.exhaustive:
        raise SystemExit("--all-candidates/--all-gfx require explicit --exhaustive")
    history_path = Path(args.history)
    output_path = Path(args.output)
    log_path = Path(args.evidence_log) if args.evidence_log else evidence_log_path(output_path)
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    existing_document = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
    logged_records = read_verification_log(log_path)
    for record in logged_records:
        apply_history_evidence(
            history,
            record.get("candidate_id"),
            record.get("result"),
            record.get("gfx"),
            record.get("python_tag"),
            record.get("platform_tag"),
            record.get("verification_id"),
            record.get("observed_at"),
            record.get("error"),
            record.get("host_platform"),
            record.get("command"),
            record.get("exit_code"),
        )
    channels = args.channels or list(DEFAULT_CHANNELS)
    targets = args.gfx or [None]
    jobs = []
    for target in targets:
        jobs.extend(matrix_jobs(history, args.platform, channels, target, args.python_tag, None if args.resume else args.limit, args.platform_tag, args.distribution_family, args.rocm, args.torch, args.all_candidates, args.all_gfx))
        if args.limit and not args.resume and len(jobs) >= args.limit:
            jobs = jobs[: args.limit]
            break
    if args.resume:
        completed_keys = completed_job_keys(output_path, history, log_path)
        jobs = [job for job in jobs if matrix_job_key(job) not in completed_keys]
        if args.limit:
            jobs = jobs[: args.limit]

    def run_job(job):
        candidate, gfx, python_tag, platform_tag = job
        worker_cache = Path(args.cache_dir) / f"worker-{threading.get_ident()}"
        return verify_candidate(candidate, gfx, args.timeout, python_tag, platform_tag, worker_cache)

    records = []
    def persist_result(index, job, record):
        candidate, gfx, python_tag, platform_tag = job
        print(f"[{index}/{len(jobs)}] Verifying {candidate['id']} for {gfx} and {python_tag}")
        records.append(record)
        append_verification_log(record, log_path)
        apply_history_evidence(
            history,
            candidate["id"],
            record["result"],
            gfx,
            python_tag,
            record["platform_tag"],
            record["id"],
            record["observed_at"],
            record.get("error"),
            record.get("host_platform"),
            record.get("command"),
            record.get("exit_code"),
        )
        print(f"    {record['result']}")

    def flush_results():
        if not (existing_document or logged_records or records):
            return
        document = merge_verification_batch(existing_document, [*logged_records, *records])
        write_json_document(document, output_path, validate_resolver_verifications)
        write_history_document(history, history_path)

    if not jobs:
        flush_results()
        raise SystemExit("No known-GFX candidates match the requested matrix")

    if args.workers == 1:
        for index, job in enumerate(jobs, 1):
            persist_result(index, job, run_job(job))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending = {executor.submit(run_job, job): job for job in jobs}
            for index, future in enumerate(as_completed(pending), 1):
                persist_result(index, pending[future], future.result())
    flush_results()
    if matrix_exit_code(records):
        failed = sum(record.get("result") == "failed" for record in records)
        raise SystemExit(f"{failed} matrix verification job(s) failed")


if __name__ == "__main__":
    main()
