import argparse
import json
import platform as host_platform_module
import re
from pathlib import Path

from .history import candidate_sort_key


def host_platform():
    return {
        "windows": "windows",
        "linux": "linux",
        "darwin": "macos",
    }.get(host_platform_module.system().lower(), "unknown")


def normalize_python_tag(value):
    if value is None:
        return None
    if re.fullmatch(r"cp\d+", value):
        return value
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if match:
        return f"cp{match.group(1)}{match.group(2)}"
    raise ValueError("Python must be formatted as cp312 or 3.12")


def resolve_candidates(history, gfx, platform=None, channel=None, rocm_version=None, torch_series=None, python_tag=None, include_unavailable=False, include_failed=False):
    python_tag = normalize_python_tag(python_tag)
    matches = []
    for candidate in history["candidates"]:
        if not include_failed:
            evidence = candidate.get("evidence_status", {})
            if evidence.get("artifact") == "artifact_stale" or evidence.get("resolver") in {"resolver_failed", "partial", "not_applicable"}:
                continue
        if candidate.get("distribution_family") == "legacy" and candidate.get("platform") == "linux" and candidate.get("framework_compatibility") != "verified":
            continue
        targets = candidate["gfx_targets"] if include_unavailable else candidate["available_gfx_targets"]
        if gfx and gfx not in targets:
            continue
        if platform and candidate.get("platform", "windows") != platform:
            continue
        if channel and candidate["channel"] != channel:
            continue
        if rocm_version and candidate["rocm_version"] != rocm_version:
            continue
        torch_base = candidate["torch_version"].split("+", 1)[0]
        if torch_series and not (torch_base == torch_series or torch_base.startswith(torch_series + ".")):
            continue
        if python_tag and python_tag not in candidate["python_tags"]:
            continue
        matches.append(candidate)
    return sorted(matches, key=candidate_sort_key, reverse=True)


def count_candidates(candidates):
    """Count distinct candidate records without changing resolver ordering."""
    seen = set()
    count = 0
    for candidate in candidates:
        identity = candidate.get("candidate_id") or candidate.get("id")
        if identity is None:
            count += 1
            continue
        if identity in seen:
            continue
        seen.add(identity)
        count += 1
    return count


def install_command(candidate, gfx):
    parts = ["python", "-m", "pip", *install_arguments(candidate, gfx)]
    return " ".join(f'"{part}"' if "[" in part else part for part in parts)


def install_arguments(candidate, gfx):
    if candidate.get("distribution_family", "therock") == "legacy":
        urls = candidate.get("wheel_urls")
        if not urls:
            raise ValueError("Legacy resolver candidates must provide direct wheel_urls")
        return ["install", "--index-url", "https://pypi.org/simple", *urls]
    if not gfx:
        raise ValueError("TheRock candidates require --gfx")
    source = candidate["source_id"].removeprefix("packages-")
    indexes = {
        "stable": "https://repo.amd.com/rocm/whl-multi-arch/",
        "nightly": "https://rocm.nightlies.amd.com/whl-multi-arch/",
        "staging": "https://rocm.nightlies.amd.com/whl-staging-multi-arch/",
        "stable-linux": "https://repo.amd.com/rocm/whl-multi-arch/",
        "nightly-linux": "https://rocm.nightlies.amd.com/whl-multi-arch/",
        "staging-linux": "https://rocm.nightlies.amd.com/whl-staging-multi-arch/",
    }
    index_url = indexes[source]
    prerelease = any(re.search(r"(?:a|b|rc|dev)\d", candidate[name]) for name in ("rocm_version", "torch_version", "torchvision_version", "torchaudio_version"))
    parts = ["install", "--index-url", index_url]
    if prerelease:
        parts.append("--pre")
    parts.extend(
        [
            f'torch[device-{gfx}]=={candidate["torch_version"]}',
            f'torchvision[device-{gfx}]=={candidate["torchvision_version"]}',
            f'torchaudio=={candidate["torchaudio_version"]}',
        ]
    )
    return parts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Resolve a historical ROCm package candidate without installing it.")
    parser.add_argument("--history", default="data/history.json")
    parser.add_argument("--gfx")
    parser.add_argument("--platform", choices=("windows", "linux", "macos", "unknown"), default=host_platform())
    parser.add_argument("--channel", choices=("stable", "nightly", "staging"))
    parser.add_argument("--rocm")
    parser.add_argument("--torch")
    parser.add_argument("--python", dest="python_tag")
    parser.add_argument("--include-unavailable", action="store_true")
    parser.add_argument("--include-failed", action="store_true", help="Include candidates with failed, partial, stale, or not-applicable evidence.")
    parser.add_argument("--all", action="store_true", dest="show_all")
    parser.add_argument("--count", action="store_true", help="Print the number of distinct matching candidates without selecting one.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    with Path(args.history).open(encoding="utf-8") as handle:
        history = json.load(handle)
    try:
        matches = resolve_candidates(
            history,
            args.gfx,
            platform=args.platform,
            channel=args.channel,
            rocm_version=args.rocm,
            torch_series=args.torch,
            python_tag=args.python_tag,
            include_unavailable=args.include_unavailable,
            include_failed=args.include_failed,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if args.count:
        count = count_candidates(matches)
        if args.json_output:
            print(json.dumps({"count": count}, sort_keys=True))
        else:
            print(f"Candidate count: {count}")
        return
    if not matches:
        raise SystemExit("No matching package candidate found")
    selected = matches if args.show_all else matches[:1]
    if args.json_output:
        print(json.dumps(selected, indent=2, sort_keys=True))
        return
    for candidate in selected:
        hip_version = candidate.get("hip_version") or "not observed"
        print(f"ROCm {candidate['rocm_version']} | HIP {hip_version} | Torch {candidate['torch_version']} | Python {', '.join(candidate['python_tags'])}")
        print(install_command(candidate, args.gfx))


if __name__ == "__main__":
    main()
