import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .documentation import collect_documentation
from .integration import build_compatibility_matrix
from .matrix_render import write_compatibility_document
from .render import write_rendered_document
from .simple_index import discover_gfx_targets, discover_packages, latest_artifacts, package_names_for_target, parse_windows_wheels
from .validation import validate_compatibility_matrix, validate_documentation_snapshot, validate_snapshot


USER_AGENT = "windows-rocm-matrix/0.1 (+https://github.com/Superple19/windows-rocm-matrix)"
BASE_PACKAGES = (
    "rocm-sdk-core",
    "rocm-sdk-libraries",
    "rocm-sdk-devel",
    "torch",
    "torchvision",
    "torchaudio",
    "triton",
)


def fetch_text(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def package_url(index_url, package_name):
    return index_url.rstrip("/") + "/" + package_name + "/"


def collect_source(source, timeout=20, workers=8, requested_gfx=()):
    index_url = source["url"]
    root_html = fetch_text(index_url, timeout)
    available_packages = discover_packages(root_html, index_url)
    available_set = set(available_packages)
    discovered_gfx = discover_gfx_targets(available_packages)

    if requested_gfx:
        unknown = sorted(set(requested_gfx) - set(discovered_gfx))
        if unknown:
            raise ValueError(f"Source {source['id']} does not list requested targets: {', '.join(unknown)}")
        gfx_targets = sorted(set(requested_gfx))
    else:
        gfx_targets = discovered_gfx

    package_names = {name for name in BASE_PACKAGES if name in available_set}
    for gfx in gfx_targets:
        package_names.update(name for name in package_names_for_target(gfx) if name in available_set)

    packages = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_text, package_url(index_url, name), timeout): name
            for name in sorted(package_names)
        }
        for future in as_completed(futures):
            name = futures[future]
            html = future.result()
            artifacts = parse_windows_wheels(html, package_url(index_url, name), name)
            packages[name] = latest_artifacts(artifacts)

    packages = {name: packages[name] for name in sorted(packages)}
    target_rows = []
    for gfx in gfx_targets:
        required = package_names_for_target(gfx)
        target_rows.append(
            {
                "gfx": gfx,
                "device_packages": list(required),
                "all_device_packages_available": all(packages.get(name) for name in required),
            }
        )

    return {
        "schema_version": 1,
        "last_observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source,
        "gfx_targets": target_rows,
        "packages": packages,
    }


def load_config(path):
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported source configuration schema")
    return config


def write_snapshot(snapshot, path):
    validate_snapshot(snapshot)
    write_json(snapshot, path)


def write_json(value, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect Windows ROCm package availability from official AMD indexes.")
    parser.add_argument("--config", default="config/sources.json")
    parser.add_argument("--output-dir", default="data/snapshots")
    parser.add_argument("--docs-output", default="docs/generated/package-availability.md")
    parser.add_argument("--documentation-output", default="data/documentation.json")
    parser.add_argument("--matrix-output", default="data/matrix.json")
    parser.add_argument("--matrix-docs-output", default="docs/generated/compatibility-matrix.md")
    parser.add_argument("--skip-documentation", action="store_true")
    parser.add_argument("--source", action="append", dest="sources", help="Collect only the named source. Repeat to select multiple sources.")
    parser.add_argument("--gfx", action="append", dest="gfx_targets", default=[], help="Collect only the exact GFX target. Repeat to select multiple targets.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    selected = set(args.sources or [])
    sources = [source for source in config["artifact_sources"] if not selected or source["id"] in selected]
    missing = selected - {source["id"] for source in sources}
    if missing:
        raise SystemExit(f"Unknown sources: {', '.join(sorted(missing))}")

    output_dir = Path(args.output_dir)
    snapshot_paths = []
    for source in sources:
        print(f"Collecting {source['id']} from {source['url']}")
        snapshot = collect_source(source, timeout=args.timeout, workers=args.workers, requested_gfx=args.gfx_targets)
        snapshot_path = output_dir / f"{source['id']}.json"
        write_snapshot(snapshot, snapshot_path)
        snapshot_paths.append(snapshot_path)
        print(f"Wrote {snapshot_path}")

    write_rendered_document(output_dir.glob("*.json"), args.docs_output)
    print(f"Wrote {args.docs_output}")

    if args.skip_documentation:
        return

    print("Collecting official compatibility documentation")
    documentation = collect_documentation(
        config["documentation_sources"],
        lambda url: fetch_text(url, args.timeout),
    )
    validate_documentation_snapshot(documentation)
    write_json(documentation, args.documentation_output)
    print(f"Wrote {args.documentation_output}")

    package_snapshots = []
    for path in sorted(output_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            package_snapshots.append(json.load(handle))
    matrix = build_compatibility_matrix(documentation, package_snapshots)
    validate_compatibility_matrix(matrix)
    write_json(matrix, args.matrix_output)
    write_compatibility_document(matrix, args.matrix_docs_output)
    print(f"Wrote {args.matrix_output}")
    print(f"Wrote {args.matrix_docs_output}")


if __name__ == "__main__":
    main()
