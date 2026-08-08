"""Run resolver dry-runs for a platform/channel/GFX/Python matrix."""

import argparse
import json
from pathlib import Path

from .resolve import resolve_candidates
from .verify import update_history_evidence, verify_candidate, write_verification


def platform_tag_for(platform, requested=None):
    if requested:
        return requested
    return {
        "linux": "manylinux_2_28_x86_64",
        "windows": "win_amd64",
        "macos": "macosx_11_0_x86_64",
    }.get(platform)


def matrix_jobs(history, platform, channels, gfx=None, python_tag=None, limit=None, platform_tag=None):
    jobs = []
    for channel in channels:
        candidates = resolve_candidates(history, None, platform=platform, channel=channel, python_tag=python_tag)
        for candidate in candidates:
            if candidate.get("distribution_family") == "legacy" and platform == "linux" and not candidate.get("available_gfx_targets"):
                python_tags = [python_tag] if python_tag else candidate["python_tags"]
                for tag in python_tags:
                    jobs.append((candidate, None, tag, platform_tag_for(platform, platform_tag)))
                    if limit and len(jobs) >= limit:
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
                    jobs.append((candidate, target, tag, platform_tag_for(platform, platform_tag)))
                    if limit and len(jobs) >= limit:
                        return jobs
    return jobs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verify ROCm package candidates across a platform matrix.")
    parser.add_argument("--history", default="data/history.json")
    parser.add_argument("--output", default="data/verifications/resolver.json")
    parser.add_argument("--platform", choices=("linux", "windows", "macos"), default="linux")
    parser.add_argument("--channel", action="append", dest="channels", choices=("stable", "nightly", "staging"))
    parser.add_argument("--gfx", action="append")
    parser.add_argument("--python", dest="python_tag")
    parser.add_argument("--platform-tag")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=900)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    channels = args.channels or ["stable", "nightly", "staging"]
    targets = args.gfx or [None]
    jobs = []
    for target in targets:
        jobs.extend(matrix_jobs(history, args.platform, channels, target, args.python_tag, args.limit, args.platform_tag))
        if args.limit and len(jobs) >= args.limit:
            jobs = jobs[: args.limit]
            break
    if not jobs:
        raise SystemExit("No known-GFX candidates match the requested matrix")
    for index, (candidate, gfx, python_tag, platform_tag) in enumerate(jobs, 1):
        print(f"[{index}/{len(jobs)}] Verifying {candidate['id']} for {gfx} and {python_tag}")
        record = verify_candidate(candidate, gfx, args.timeout, python_tag, platform_tag)
        write_verification(record, args.output)
        update_history_evidence(args.history, candidate["id"], record["result"], gfx, python_tag, record["platform_tag"], record["id"], record["observed_at"])
        print(f"    {record['result']}")


if __name__ == "__main__":
    main()
