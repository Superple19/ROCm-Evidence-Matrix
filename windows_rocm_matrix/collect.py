import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .documentation import collect_documentation_sources
from .ci import build_evidence, collect_github, collect_hud, parse_matrix
from .catalog import write_catalog
from .history import attach_therock_ci_evidence, build_history_observations, merge_history, write_history_document
from .integration import build_compatibility_matrix
from .legacy import build_legacy_candidates, collect_legacy_windows_sources, render_legacy_windows
from .legacy_linux import build_legacy_linux_candidates, collect_legacy_linux_sources, render_legacy_linux
from .matrix_render import write_compatibility_document
from .render import write_rendered_document
from .simple_index import discover_gfx_targets, discover_packages, latest_artifacts, package_names_for_target, parse_package_artifacts
from .source_cache import CachedSourceReader, SourceCache
from .source_adapter import collection_status, run_source_adapter, utc_now
from .validation import validate_ci_coverage, validate_ci_evidence, validate_collection_status, validate_compatibility_matrix, validate_documentation_snapshot, validate_history, validate_legacy_linux, validate_legacy_windows, validate_snapshot, validate_version_history
from .version_history import collect_legacy_version_history, collect_therock_version_history, render_version_history


USER_AGENT = "rocm-matrix/0.1 (+https://github.com/Superple19/windows-rocm-matrix)"
BASE_PACKAGES = (
    "rocm",
    "rocm-sdk-core",
    "rocm-sdk-libraries",
    "rocm-sdk-devel",
    "torch",
    "torchvision",
    "torchaudio",
    "triton",
)


def fetch_text(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json, application/json;q=0.9, text/html;q=0.8"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def memoized_reader(reader):
    responses = {}

    def read(url):
        if url not in responses:
            responses[url] = reader(url)
        return responses[url]

    return read


def package_url(index_url, package_name):
    return index_url.rstrip("/") + "/" + package_name + "/"


def collect_source(source, timeout=20, workers=8, requested_gfx=(), framework_compatibility=(), fetch=None, observed_at=None):
    fetch = fetch or (lambda url: fetch_text(url, timeout))
    index_url = source["url"]
    root_html = fetch(index_url)
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

    all_packages = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch, package_url(index_url, name)): name
            for name in sorted(package_names)
        }
        for future in as_completed(futures):
            name = futures[future]
            html = future.result()
            all_packages[name] = parse_package_artifacts(html, package_url(index_url, name), name, source.get("platform", "windows"))

    all_packages = {name: all_packages[name] for name in sorted(all_packages)}
    packages = {name: latest_artifacts(artifacts) for name, artifacts in all_packages.items()}
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

    snapshot = {
        "schema_version": 1,
        "last_observed_at": observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {**source, "platform": source.get("platform", "windows")},
        "gfx_targets": target_rows,
        "packages": packages,
    }
    history = build_history_observations(
        source,
        gfx_targets,
        all_packages,
        framework_compatibility,
        source.get("distribution_family", "therock"),
    ) if framework_compatibility else []
    return snapshot, history


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


def add_config_path(parser):
    parser.add_argument("--config", default="config/sources.json")


def add_cache_paths(parser):
    parser.add_argument("--cache-dir", default=".cache/sources")
    parser.add_argument("--source-manifest", default="data/observations/source-manifest.json")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect and build platform-aware ROCm compatibility evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    collect_parser = commands.add_parser("collect", help="Collect one distribution family from official sources.")
    families = collect_parser.add_subparsers(dest="family", required=True)

    therock = families.add_parser("therock", help="Collect TheRock documentation and package indexes.")
    add_config_path(therock)
    add_cache_paths(therock)
    therock.add_argument("--output-dir", default="data/snapshots")
    therock.add_argument("--documentation-output", default="data/documentation.json")
    therock.add_argument("--history-output", default="data/history.json")
    therock.add_argument("--version-history-output", default="data/version-history.json")
    therock.add_argument("--status-output", default="data/status/therock.json")
    therock.add_argument("--ci-coverage-output", default="data/ci-coverage.json")
    therock.add_argument("--ci-evidence-output", default="data/ci-evidence.json")
    therock.add_argument("--source", action="append", dest="sources", help="Collect only the named package source. Repeat to select multiple sources.")
    therock.add_argument("--gfx", action="append", dest="gfx_targets", default=[], help="Collect only the exact GFX target. Repeat to select multiple targets.")
    therock.add_argument("--timeout", type=int, default=20)
    therock.add_argument("--workers", type=int, default=8)

    legacy = families.add_parser("legacy", help="Collect pre-TheRock Windows documentation and package repositories.")
    add_config_path(legacy)
    add_cache_paths(legacy)
    legacy.add_argument("--legacy-output", default="data/legacy-windows.json")
    legacy.add_argument("--legacy-linux-output", default="data/legacy-linux.json")
    legacy.add_argument("--version-history-output", default="data/version-history.json")
    legacy.add_argument("--status-output", default="data/status/legacy.json")
    legacy.add_argument("--timeout", type=int, default=20)

    normalize_parser = commands.add_parser("normalize", help="Rebuild normalized evidence from cached source responses without network access.")
    normalizers = normalize_parser.add_subparsers(dest="family", required=True)

    normalize_therock = normalizers.add_parser("therock", help="Normalize cached TheRock documentation and package indexes.")
    add_config_path(normalize_therock)
    add_cache_paths(normalize_therock)
    normalize_therock.add_argument("--output-dir", default="data/snapshots")
    normalize_therock.add_argument("--documentation-output", default="data/documentation.json")
    normalize_therock.add_argument("--history-output", default="data/history.json")
    normalize_therock.add_argument("--version-history-output", default="data/version-history.json")
    normalize_therock.add_argument("--source", action="append", dest="sources", help="Normalize only the named package source. Repeat to select multiple sources.")
    normalize_therock.add_argument("--gfx", action="append", dest="gfx_targets", default=[], help="Normalize only the exact GFX target. Repeat to select multiple targets.")
    normalize_therock.add_argument("--workers", type=int, default=8)
    normalize_therock.add_argument("--ci-coverage-output", default="data/ci-coverage.json")
    normalize_therock.add_argument("--ci-evidence-output", default="data/ci-evidence.json")

    normalize_legacy = normalizers.add_parser("legacy", help="Normalize cached pre-TheRock Windows sources.")
    add_config_path(normalize_legacy)
    add_cache_paths(normalize_legacy)
    normalize_legacy.add_argument("--legacy-output", default="data/legacy-windows.json")
    normalize_legacy.add_argument("--legacy-linux-output", default="data/legacy-linux.json")
    normalize_legacy.add_argument("--version-history-output", default="data/version-history.json")

    integrate = commands.add_parser("integrate", help="Build the integrated matrix from normalized evidence without network access.")
    integrate.add_argument("--output-dir", default="data/snapshots")
    integrate.add_argument("--documentation-output", default="data/documentation.json")
    integrate.add_argument("--matrix-output", default="data/matrix.json")

    render = commands.add_parser("render", help="Render documentation from normalized and integrated data without network access.")
    render.add_argument("--output-dir", default="data/snapshots")
    render.add_argument("--history-output", default="data/history.json")
    render.add_argument("--legacy-output", default="data/legacy-windows.json")
    render.add_argument("--version-history-output", default="data/version-history.json")
    render.add_argument("--matrix-output", default="data/matrix.json")
    render.add_argument("--docs-output", default="docs/generated/package-availability.md")
    render.add_argument("--matrix-docs-output", default="docs/generated/compatibility-matrix.md")
    render.add_argument("--history-docs-output", default="docs/generated/history.md")
    render.add_argument("--legacy-docs-output", default="docs/generated/legacy-windows.md")
    render.add_argument("--legacy-linux-output", default="data/legacy-linux.json")
    render.add_argument("--legacy-linux-docs-output", default="docs/generated/legacy-linux.md")
    render.add_argument("--version-history-docs-output", default="docs/generated/version-history.md")

    build = commands.add_parser("build", help="Build integrated JSON and Markdown from collected data without network access.")
    build.add_argument("--output-dir", default="data/snapshots")
    build.add_argument("--documentation-output", default="data/documentation.json")
    build.add_argument("--history-output", default="data/history.json")
    build.add_argument("--ci-evidence-output", default="data/ci-evidence.json")
    build.add_argument("--legacy-output", default="data/legacy-windows.json")
    build.add_argument("--version-history-output", default="data/version-history.json")
    build.add_argument("--docs-output", default="docs/generated/package-availability.md")
    build.add_argument("--matrix-output", default="data/matrix.json")
    build.add_argument("--matrix-docs-output", default="docs/generated/compatibility-matrix.md")
    build.add_argument("--history-docs-output", default="docs/generated/history.md")
    build.add_argument("--legacy-docs-output", default="docs/generated/legacy-windows.md")
    build.add_argument("--legacy-linux-output", default="data/legacy-linux.json")
    build.add_argument("--legacy-linux-docs-output", default="docs/generated/legacy-linux.md")
    build.add_argument("--version-history-docs-output", default="docs/generated/version-history.md")
    catalog = commands.add_parser("catalog", help="Write the machine-readable artifact catalog without network access.")
    catalog.add_argument("--root", default=".")
    catalog.add_argument("--output", default="data/catalog.json")
    runtime = commands.add_parser("runtime", help="Record ROCm runtime evidence from the current Python environment.")
    runtime.add_argument("--output", default="data/verifications/runtime.json")
    hardware = commands.add_parser("hardware", help="Run a reproducible ROCm GPU tensor smoke test.")
    hardware.add_argument("--output", default="data/verifications/hardware.json")
    return parser.parse_args(argv)


def read_json(path):
    path = Path(path)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_status(family, started_at, results, path):
    status = collection_status(family, started_at, results)
    validate_collection_status(status)
    write_json(status, path)
    return status


def normalize_therock_sources(args, config, source_reader, observed_at, status_output=None):
    source_reader = memoized_reader(source_reader)
    started_at = utc_now()
    existing_documentation = read_json(args.documentation_output)
    documentation, results = collect_documentation_sources(
        config["documentation_sources"],
        source_reader,
        existing=existing_documentation,
        observed_at=observed_at,
    )
    if any(result["status"] == "passed" for result in results):
        validate_documentation_snapshot(documentation)
        write_json(documentation, args.documentation_output)
        print(f"Wrote {args.documentation_output}")
    for result in results:
        if result["status"] == "failed":
            print(f"Failed {result['source_id']}: {result['error']}")

    version_config = config.get("version_history_sources", {}).get("therock")
    if version_config:
        version_history_path = getattr(args, "version_history_output", "data/version-history.json")
        version_history, version_results = collect_therock_version_history(
            version_config,
            source_reader,
            documentation["therock_windows_status"],
            existing=read_json(version_history_path),
            observed_at=observed_at,
        )
        results.extend(version_results)
        if any(result["status"] == "passed" for result in version_results):
            validate_version_history(version_history)
            write_json(version_history, version_history_path)
            print(f"Wrote {version_history_path}")

    selected = set(args.sources or [])
    sources = [source for source in config["artifact_sources"] if not selected or source["id"] in selected]
    missing = selected - {source["id"] for source in sources}
    if missing:
        raise SystemExit(f"Unknown sources: {', '.join(sorted(missing))}")

    output_dir = Path(args.output_dir)
    history_observations = []
    successful_sources = []
    for source in sources:
        print(f"Processing {source['id']} from {source['url']}")
        collected, result = run_source_adapter(
            source,
            lambda source=source: collect_source(
                source,
                timeout=getattr(args, "timeout", 20),
                workers=args.workers,
                requested_gfx=args.gfx_targets,
                framework_compatibility=documentation["framework_compatibility"],
                fetch=source_reader,
                observed_at=observed_at,
            ),
        )
        results.append(result)
        if collected is None:
            print(f"Failed {source['id']}: {result['error']}")
            continue
        snapshot, observations = collected
        snapshot_path = output_dir / f"{source['id']}.json"
        write_snapshot(snapshot, snapshot_path)
        history_observations.extend(observations)
        successful_sources.append(source)
        print(f"Wrote {snapshot_path}")

    if successful_sources:
        package_snapshots = [read_json(path) for path in sorted(output_dir.glob("*.json"))]
        existing_history = read_json(args.history_output)
        package_sources = {
            f"packages-{snapshot['source']['id']}": {**snapshot["source"], "distribution_family": "therock", "observed_at": snapshot["last_observed_at"]}
            for snapshot in package_snapshots
        }
        history = merge_history(
            existing_history,
            history_observations,
            package_sources,
            max(snapshot["last_observed_at"] for snapshot in package_snapshots),
            {f"packages-{source['id']}" for source in successful_sources},
        )
        validate_history(history)
        write_json(history, args.history_output)
        print(f"Wrote {args.history_output}")

    ci_config = config.get("ci_sources", {}).get("therock")
    if ci_config:
        ci_results = []
        coverage = None
        try:
            coverage = parse_matrix(source_reader(ci_config["matrix"]["url"]), observed_at)
            validate_ci_coverage(coverage)
            write_json(coverage, args.ci_coverage_output)
            print(f"Wrote {args.ci_coverage_output}")
            ci_results.append({"source_id": ci_config["matrix"]["id"], "status": "passed", "error": None})
        except Exception as error:
            ci_results.append({"source_id": ci_config["matrix"]["id"], "status": "failed", "error": str(error)})
            print(f"Failed {ci_config['matrix']['id']}: {error}")
        records = []
        failures = []
        for adapter_name, adapter in (("github_actions", lambda: collect_github(ci_config, source_reader, observed_at)), ("hud", lambda: collect_hud(ci_config["hud"], source_reader, observed_at))):
            try:
                records.extend(adapter())
                ci_results.append({"source_id": ci_config["workflows"]["id"] if adapter_name == "github_actions" else ci_config["hud"]["id"], "status": "passed", "error": None})
            except Exception as error:
                failure = {"adapter": adapter_name, "error": str(error), "observed_at": observed_at}
                failures.append(failure)
                ci_results.append({"source_id": ci_config["workflows"]["id"] if adapter_name == "github_actions" else ci_config["hud"]["id"], "status": "failed", "error": str(error)})
                print(f"Failed {adapter_name}: {error}")
        evidence = build_evidence(records, [], existing=read_json(args.ci_evidence_output), observed_at=observed_at, failures=failures)
        validate_ci_evidence(evidence)
        write_json(evidence, args.ci_evidence_output)
        print(f"Wrote {args.ci_evidence_output}")
        history = read_json(args.history_output)
        if history is not None:
            attach_therock_ci_evidence(history, evidence)
            validate_history(history)
            write_json(history, args.history_output)
            print(f"Updated {args.history_output} with CI evidence")
        results.extend(ci_results)

    if status_output:
        status = write_status("therock", started_at, results, status_output)
        print(f"Wrote {status_output}")
        results = status["results"]
    return all(result["status"] == "passed" for result in results)


def collect_therock(args, config):
    source_cache = SourceCache(args.cache_dir, args.source_manifest, args.timeout)
    success = normalize_therock_sources(args, config, source_cache, source_cache.generated_at, args.status_output)
    source_cache.write_manifest()
    print(f"Wrote {args.source_manifest}")
    return success


def normalize_therock(args, config):
    source_reader = CachedSourceReader(args.cache_dir, args.source_manifest)
    documentation_urls = [source["url"] for source in config["documentation_sources"]]
    selected = set(args.sources or [])
    artifact_prefixes = [source["url"] for source in config["artifact_sources"] if not selected or source["id"] in selected]
    version_sources = config.get("version_history_sources", {}).get("therock")
    if version_sources:
        documentation_urls.extend((version_sources["releases"]["url"], version_sources["version"]["url"]))
    observed_at = source_reader.latest_observed_at(documentation_urls, artifact_prefixes)
    return normalize_therock_sources(args, config, source_reader, observed_at)


def normalize_legacy_sources(args, config, source_reader, observed_at, status_output=None):
    source_reader = memoized_reader(source_reader)
    started_at = utc_now()
    existing = read_json(args.legacy_output)
    legacy, results = collect_legacy_windows_sources(
        config["legacy_windows_sources"],
        source_reader,
        existing=existing,
        observed_at=observed_at,
    )
    if any(result["status"] == "passed" for result in results):
        validate_legacy_windows(legacy)
        write_json(legacy, args.legacy_output)
        print(f"Wrote {args.legacy_output}")
        history_path = getattr(args, "history_output", "data/history.json")
        legacy_candidates = build_legacy_candidates(legacy)
        legacy_source = {
            "id": "legacy-artifacts",
            "distribution_family": "legacy",
            "platform": "windows",
            "channel": "stable",
            "url": config["legacy_windows_sources"]["artifact_index"]["url"],
            "observed_at": observed_at,
        }
        history = merge_history(
            read_json(history_path),
            legacy_candidates,
            {"legacy-artifacts": legacy_source},
            observed_at,
            {"legacy-artifacts"},
        )
        validate_history(history)
        write_json(history, history_path)
        print(f"Wrote {history_path}")
    for result in results:
        if result["status"] == "failed":
            print(f"Failed {result['source_id']}: {result['error']}")
    linux_sources = config.get("legacy_linux_sources", [])
    if linux_sources:
        legacy_linux, linux_results = collect_legacy_linux_sources(
            linux_sources,
            source_reader,
            existing=read_json(args.legacy_linux_output),
            observed_at=observed_at,
        )
        results.extend(linux_results)
        if any(result["status"] == "passed" for result in linux_results):
            validate_legacy_linux(legacy_linux)
            write_json(legacy_linux, args.legacy_linux_output)
            print(f"Wrote {args.legacy_linux_output}")
            history_path = getattr(args, "history_output", "data/history.json")
            legacy_linux_source = {
                "id": "legacy-linux-artifacts",
                "distribution_family": "legacy",
                "platform": "linux",
                "channel": "stable",
                "url": linux_sources[0]["url"],
                "observed_at": observed_at,
            }
            history = merge_history(
                read_json(history_path),
                build_legacy_linux_candidates(legacy_linux),
                {"legacy-linux-artifacts": legacy_linux_source},
                observed_at,
                {"legacy-linux-artifacts"},
            )
            validate_history(history)
            write_json(history, history_path)
            print(f"Wrote {history_path}")
        for result in linux_results:
            if result["status"] == "failed":
                print(f"Failed {result['source_id']}: {result['error']}")
    version_config = config.get("version_history_sources", {}).get("legacy")
    if version_config:
        version_history_path = getattr(args, "version_history_output", "data/version-history.json")
        version_history, version_results = collect_legacy_version_history(
            version_config,
            source_reader,
            legacy,
            existing=read_json(version_history_path),
            observed_at=observed_at,
        )
        results.extend(version_results)
        if any(result["status"] == "passed" for result in version_results):
            validate_version_history(version_history)
            write_json(version_history, version_history_path)
            print(f"Wrote {version_history_path}")
    if status_output:
        status = write_status("legacy", started_at, results, status_output)
        print(f"Wrote {status_output}")
        results = status["results"]
    return all(result["status"] == "passed" for result in results)


def collect_legacy(args, config):
    source_cache = SourceCache(args.cache_dir, args.source_manifest, args.timeout)
    success = normalize_legacy_sources(args, config, source_cache, source_cache.generated_at, args.status_output)
    source_cache.write_manifest()
    print(f"Wrote {args.source_manifest}")
    return success


def normalize_legacy(args, config):
    source_reader = CachedSourceReader(args.cache_dir, args.source_manifest)
    sources = config["legacy_windows_sources"]
    source_urls = [sources["hip_sdk_release_versions"]["url"]]
    source_urls.extend(source["url"] for source in sources["hip_sdk_gpu_support"])
    source_urls.extend(source["url"] for source in sources["pytorch_windows_support"])
    version_sources = config.get("version_history_sources", {}).get("legacy")
    if version_sources:
        source_urls.extend((version_sources["rocm_releases"]["url"], version_sources["documentation_branches"]["url"]))
    observed_at = source_reader.latest_observed_at(source_urls, [sources["artifact_index"]["url"]])
    return normalize_legacy_sources(args, config, source_reader, observed_at)


def load_package_snapshots(output_dir):
    snapshot_paths = sorted(Path(output_dir).glob("*.json"))
    if not snapshot_paths:
        raise SystemExit("Package snapshots are required")
    package_snapshots = [read_json(path) for path in snapshot_paths]
    for snapshot in package_snapshots:
        validate_snapshot(snapshot)
    return snapshot_paths, package_snapshots


def integrate_outputs(args):
    documentation = read_json(args.documentation_output)
    if documentation is None:
        raise SystemExit("Normalized documentation evidence is required before integration")
    validate_documentation_snapshot(documentation)
    _, package_snapshots = load_package_snapshots(args.output_dir)
    matrix = build_compatibility_matrix(documentation, package_snapshots)
    validate_compatibility_matrix(matrix)
    write_json(matrix, args.matrix_output)
    print(f"Wrote {args.matrix_output}")


def render_outputs(args):
    history = read_json(args.history_output)
    legacy = read_json(args.legacy_output)
    matrix = read_json(args.matrix_output)
    version_history = read_json(args.version_history_output)
    if history is None or legacy is None or matrix is None or version_history is None:
        raise SystemExit("Integrated matrix, history, legacy evidence, and version history are required before rendering")
    validate_history(history)
    validate_legacy_windows(legacy)
    validate_compatibility_matrix(matrix)
    validate_version_history(version_history)
    snapshot_paths, _ = load_package_snapshots(args.output_dir)

    write_rendered_document(snapshot_paths, args.docs_output)
    write_history_document(history, args.history_docs_output)
    write_compatibility_document(matrix, args.matrix_docs_output)
    legacy_path = Path(args.legacy_docs_output)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(render_legacy_windows(legacy), encoding="utf-8", newline="\n")
    legacy_linux = read_json(args.legacy_linux_output)
    if legacy_linux is not None:
        legacy_linux_path = Path(args.legacy_linux_docs_output)
        legacy_linux_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_linux_path.write_text(render_legacy_linux(legacy_linux), encoding="utf-8", newline="\n")
    version_history_path = Path(args.version_history_docs_output)
    version_history_path.parent.mkdir(parents=True, exist_ok=True)
    version_history_path.write_text(render_version_history(version_history), encoding="utf-8", newline="\n")
    paths = (args.docs_output, args.history_docs_output, args.matrix_docs_output, args.legacy_docs_output, args.version_history_docs_output)
    if legacy_linux is not None:
        paths += (args.legacy_linux_docs_output,)
    for path in paths:
        print(f"Wrote {path}")


def build_outputs(args):
    integrate_outputs(args)
    history = read_json(args.history_output)
    ci_evidence = read_json(args.ci_evidence_output)
    if history is not None and ci_evidence is not None:
        attach_therock_ci_evidence(history, ci_evidence)
        validate_history(history)
        write_json(history, args.history_output)
        print(f"Updated {args.history_output} with CI evidence")
    render_outputs(args)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "runtime":
        from .runtime import main as runtime_main
        runtime_main(["--output", args.output])
        return
    if args.command == "hardware":
        from .hardware import main as hardware_main
        hardware_main(["--output", args.output])
        return
    if args.command == "build":
        build_outputs(args)
        return
    if args.command == "catalog":
        print(f"Wrote {write_catalog(args.root, args.output)}")
        return
    if args.command == "integrate":
        integrate_outputs(args)
        return
    if args.command == "render":
        render_outputs(args)
        return
    config = load_config(args.config)
    if args.command == "collect":
        success = collect_therock(args, config) if args.family == "therock" else collect_legacy(args, config)
    else:
        success = normalize_therock(args, config) if args.family == "therock" else normalize_legacy(args, config)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
