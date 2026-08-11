import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .sources.therock import build_evidence, collect_documentation_sources, collect_github, collect_hud, collect_source, parse_matrix
from .catalog import write_catalog
from .extension_catalog import rebuild_extension_catalog, render_extension_catalog
from .extension_sources import collect_extension_sources, rebuild_extension_catalog_from_sources
from .extensions import rebuild_extension_history, render_extension_history
from .history import attach_therock_ci_evidence, attach_therock_documentation_evidence, merge_history, migrate_history, write_history_document
from .frameworks import rebuild_auxiliary_outputs, render_framework_history, render_sdk_components
from .integration import build_compatibility_matrix
from .sources.legacy_archive import build_legacy_candidates, build_legacy_linux_candidates, classify_legacy_linux_framework, collect_legacy_linux_sources, collect_legacy_version_history, collect_legacy_windows_sources, render_legacy_linux, render_legacy_windows
from .matrix_render import write_compatibility_document
from .paths import EXTENSION_ARTIFACT_HISTORY, EXTENSION_CATALOG, EXTENSION_SNAPSHOTS, LEGACY_LINUX, LEGACY_LINUX_DOC, LEGACY_STATUS, LEGACY_WINDOWS, LEGACY_WINDOWS_DOC, THEROCK_CI_COVERAGE, THEROCK_CI_EVIDENCE, THEROCK_SNAPSHOTS, THEROCK_STATUS
from .render import write_rendered_document
from .source_cache import CachedSourceReader, SourceCache
from .source_adapter import collection_status, run_source_adapter, utc_now
from .persistence import atomic_write_json, atomic_write_text
from .validation import validate_ci_coverage, validate_ci_evidence, validate_collection_status, validate_compatibility_matrix, validate_documentation_snapshot, validate_extension_catalog, validate_history, validate_legacy_linux, validate_legacy_windows, validate_snapshot, validate_version_history
from .version_history import collect_therock_version_history, render_version_history


USER_AGENT = "rocm-evidence-matrix/0.1 (+https://github.com/Superple19/rocm-evidence-matrix)"


def _error_details(error):
    details = getattr(error, "details", None)
    return details if isinstance(details, dict) else None


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
    atomic_write_json(value, path)


def add_config_path(parser):
    parser.add_argument("--config", default="config/sources.json")


def add_cache_paths(parser):
    parser.add_argument("--cache-dir", default=".cache/sources")
    parser.add_argument("--source-manifest", default="data/observations/source-manifest.json")


def add_auxiliary_paths(parser):
    parser.add_argument("--framework-history-output", default="data/framework-history.json")
    parser.add_argument("--sdk-components-output", default="data/sdk-components.json")
    parser.add_argument("--extension-history-output", default="data/extension-history.json")
    parser.add_argument("--extension-catalog-output", default=EXTENSION_CATALOG)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect and build platform-aware ROCm compatibility evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    collect_parser = commands.add_parser("collect", help="Collect one distribution family from official sources.")
    families = collect_parser.add_subparsers(dest="family", required=True)

    therock = families.add_parser("therock", help="Collect TheRock documentation and package indexes.")
    add_config_path(therock)
    add_cache_paths(therock)
    add_auxiliary_paths(therock)
    therock.add_argument("--output-dir", default=THEROCK_SNAPSHOTS)
    therock.add_argument("--documentation-output", default="data/documentation.json")
    therock.add_argument("--history-output", default="data/history.json")
    therock.add_argument("--version-history-output", default="data/version-history.json")
    therock.add_argument("--status-output", default=THEROCK_STATUS)
    therock.add_argument("--ci-coverage-output", default=THEROCK_CI_COVERAGE)
    therock.add_argument("--ci-evidence-output", default=THEROCK_CI_EVIDENCE)
    therock.add_argument("--source", action="append", dest="sources", help="Collect only the named package source. Repeat to select multiple sources.")
    therock.add_argument("--gfx", action="append", dest="gfx_targets", default=[], help="Collect only the exact GFX target. Repeat to select multiple targets.")
    therock.add_argument("--timeout", type=int, default=20)
    therock.add_argument("--workers", type=int, default=8)

    legacy = families.add_parser("legacy", help="Explicitly refresh archive-only pre-TheRock evidence.")
    add_config_path(legacy)
    add_cache_paths(legacy)
    legacy.add_argument("--legacy-output", default=LEGACY_WINDOWS)
    legacy.add_argument("--legacy-linux-output", default=LEGACY_LINUX)
    legacy.add_argument("--documentation-output", default="data/documentation.json")
    legacy.add_argument("--version-history-output", default="data/version-history.json")
    legacy.add_argument("--status-output", default=LEGACY_STATUS)
    legacy.add_argument("--timeout", type=int, default=20)

    extensions = families.add_parser("extensions", help="Collect external ComfyUI extension package artifacts.")
    add_config_path(extensions)
    add_cache_paths(extensions)
    extensions.add_argument("--output-dir", default=EXTENSION_SNAPSHOTS)
    extensions.add_argument("--catalog-output", default=EXTENSION_CATALOG)
    extensions.add_argument("--history-output", default=EXTENSION_ARTIFACT_HISTORY)
    extensions.add_argument("--status-output", default="data/extensions/status.json")
    extensions.add_argument("--source", action="append", dest="sources", help="Collect only the named extension source. Repeat to select multiple sources.")
    extensions.add_argument("--timeout", type=int, default=20)

    normalize_parser = commands.add_parser("normalize", help="Rebuild normalized evidence from cached source responses without network access.")
    normalizers = normalize_parser.add_subparsers(dest="family", required=True)

    normalize_therock = normalizers.add_parser("therock", help="Normalize cached TheRock documentation and package indexes.")
    add_config_path(normalize_therock)
    add_cache_paths(normalize_therock)
    add_auxiliary_paths(normalize_therock)
    normalize_therock.add_argument("--output-dir", default=THEROCK_SNAPSHOTS)
    normalize_therock.add_argument("--documentation-output", default="data/documentation.json")
    normalize_therock.add_argument("--history-output", default="data/history.json")
    normalize_therock.add_argument("--version-history-output", default="data/version-history.json")
    normalize_therock.add_argument("--source", action="append", dest="sources", help="Normalize only the named package source. Repeat to select multiple sources.")
    normalize_therock.add_argument("--gfx", action="append", dest="gfx_targets", default=[], help="Normalize only the exact GFX target. Repeat to select multiple targets.")
    normalize_therock.add_argument("--workers", type=int, default=8)
    normalize_therock.add_argument("--ci-coverage-output", default=THEROCK_CI_COVERAGE)
    normalize_therock.add_argument("--ci-evidence-output", default=THEROCK_CI_EVIDENCE)

    normalize_legacy = normalizers.add_parser("legacy", help="Normalize cached archive-only pre-TheRock sources.")
    add_config_path(normalize_legacy)
    add_cache_paths(normalize_legacy)
    normalize_legacy.add_argument("--legacy-output", default=LEGACY_WINDOWS)
    normalize_legacy.add_argument("--legacy-linux-output", default=LEGACY_LINUX)
    normalize_legacy.add_argument("--documentation-output", default="data/documentation.json")
    normalize_legacy.add_argument("--version-history-output", default="data/version-history.json")

    normalize_extensions = normalizers.add_parser("extensions", help="Normalize cached external extension sources without network access.")
    add_config_path(normalize_extensions)
    add_cache_paths(normalize_extensions)
    add_auxiliary_paths(normalize_extensions)
    normalize_extensions.add_argument("--output-dir", default=EXTENSION_SNAPSHOTS)
    normalize_extensions.add_argument("--catalog-output", default=EXTENSION_CATALOG)
    normalize_extensions.add_argument("--history-output", default=EXTENSION_ARTIFACT_HISTORY)

    integrate = commands.add_parser("integrate", help="Build the integrated matrix from normalized evidence without network access.")
    integrate.add_argument("--output-dir", default=THEROCK_SNAPSHOTS)
    integrate.add_argument("--documentation-output", default="data/documentation.json")
    integrate.add_argument("--matrix-output", default="data/matrix.json")

    render = commands.add_parser("render", help="Render documentation from normalized and integrated data without network access.")
    render.add_argument("--output-dir", default=THEROCK_SNAPSHOTS)
    render.add_argument("--history-output", default="data/history.json")
    render.add_argument("--legacy-output", default=LEGACY_WINDOWS)
    render.add_argument("--version-history-output", default="data/version-history.json")
    render.add_argument("--matrix-output", default="data/matrix.json")
    render.add_argument("--docs-output", default="docs/generated/package-availability.md")
    render.add_argument("--matrix-docs-output", default="docs/generated/compatibility-matrix.md")
    render.add_argument("--history-docs-output", default="docs/generated/history.md")
    render.add_argument("--legacy-docs-output", default=LEGACY_WINDOWS_DOC)
    render.add_argument("--legacy-linux-output", default=LEGACY_LINUX)
    render.add_argument("--legacy-linux-docs-output", default=LEGACY_LINUX_DOC)
    render.add_argument("--version-history-docs-output", default="docs/generated/version-history.md")
    add_auxiliary_paths(render)

    build = commands.add_parser("build", help="Build integrated JSON and Markdown from collected data without network access.")
    build.add_argument("--output-dir", default=THEROCK_SNAPSHOTS)
    build.add_argument("--documentation-output", default="data/documentation.json")
    build.add_argument("--history-output", default="data/history.json")
    build.add_argument("--ci-evidence-output", default=THEROCK_CI_EVIDENCE)
    build.add_argument("--legacy-output", default=LEGACY_WINDOWS)
    build.add_argument("--version-history-output", default="data/version-history.json")
    build.add_argument("--docs-output", default="docs/generated/package-availability.md")
    build.add_argument("--matrix-output", default="data/matrix.json")
    build.add_argument("--matrix-docs-output", default="docs/generated/compatibility-matrix.md")
    build.add_argument("--history-docs-output", default="docs/generated/history.md")
    build.add_argument("--legacy-docs-output", default=LEGACY_WINDOWS_DOC)
    build.add_argument("--legacy-linux-output", default=LEGACY_LINUX)
    build.add_argument("--legacy-linux-docs-output", default=LEGACY_LINUX_DOC)
    build.add_argument("--version-history-docs-output", default="docs/generated/version-history.md")
    add_auxiliary_paths(build)
    catalog = commands.add_parser("catalog", help="Write the machine-readable artifact catalog without network access.")
    catalog.add_argument("--root", default=".")
    catalog.add_argument("--output", default="data/catalog.json")
    check = commands.add_parser("check", help="Validate committed evidence and generated documentation without network access.")
    check.add_argument("--root", default=".")
    runtime = commands.add_parser("runtime", help="Record ROCm runtime evidence from the current Python environment.")
    runtime.add_argument("--output", default="data/verifications/runtime.json")
    runtime.add_argument("--candidate-id")
    runtime.add_argument("--gfx")
    runtime.add_argument("--history", default="data/history.json")
    hardware = commands.add_parser("hardware", help="Run a reproducible ROCm GPU tensor smoke test.")
    hardware.add_argument("--output", default="data/verifications/hardware.json")
    hardware.add_argument("--candidate-id")
    hardware.add_argument("--gfx")
    hardware.add_argument("--history", default="data/history.json")
    return parser.parse_args(argv)


def read_json(path) -> dict[str, Any] | None:
    path = Path(path)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_required_json(path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object at {path}")
    return value


def write_status(family, started_at, results, path):
    status = collection_status(family, started_at, results)
    validate_collection_status(status)
    write_json(status, path)
    return status


def auxiliary_paths(args):
    output_dir = Path(getattr(args, "output_dir", THEROCK_SNAPSHOTS))
    default_dir = output_dir.parent
    framework_path = getattr(args, "framework_history_output", None) or default_dir / "framework-history.json"
    components_path = getattr(args, "sdk_components_output", None) or default_dir / "sdk-components.json"
    extension_path = getattr(args, "extension_history_output", None) or default_dir / "extension-history.json"
    return Path(framework_path), Path(components_path), Path(extension_path)


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
        package_snapshots = [read_required_json(path) for path in sorted(output_dir.glob("*.json"))]
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
            args.gfx_targets,
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
                details = _error_details(error)
                failure = {"adapter": adapter_name, "error": str(error), "observed_at": observed_at}
                if details:
                    failure["details"] = details
                failures.append(failure)
                ci_results.append({"source_id": ci_config["workflows"]["id"] if adapter_name == "github_actions" else ci_config["hud"]["id"], "status": "failed", "error": str(error), **({"details": details} if details else {})})
                print(f"Failed {adapter_name}: {error}")
        evidence = build_evidence(records, [], existing=read_json(args.ci_evidence_output), observed_at=observed_at, failures=failures)
        validate_ci_evidence(evidence)
        write_json(evidence, args.ci_evidence_output)
        print(f"Wrote {args.ci_evidence_output}")
        history = read_json(args.history_output)
        if history is not None:
            attach_therock_documentation_evidence(history, documentation)
            attach_therock_ci_evidence(history, evidence)
            validate_history(history)
            write_json(history, args.history_output)
        print(f"Updated {args.history_output} with CI evidence")
        results.extend(ci_results)

    if successful_sources:
        framework_path, components_path, extension_path = auxiliary_paths(args)
        rebuild_auxiliary_outputs(args.output_dir, framework_path, components_path, observed_at, read_json, write_json)
        rebuild_extension_history(args.output_dir, extension_path, observed_at, read_json, write_json, read_json(args.history_output))
        extension_catalog_output = getattr(args, "extension_catalog_output", None)
        if extension_catalog_output is None:
            extension_catalog_output = str(Path(args.output_dir).parent / "extensions" / "catalog.json")
        extension_catalog = rebuild_extension_catalog(
            args.output_dir,
            extension_catalog_output,
            observed_at,
            read_json,
            extension_snapshot_dir=Path(extension_catalog_output).parent / "snapshots",
            history_path=Path(extension_catalog_output).parent / "history.json",
        )
        validate_extension_catalog(extension_catalog)
        print(f"Wrote {framework_path}")
        print(f"Wrote {components_path}")
        print(f"Wrote {extension_path}")
        print(f"Wrote {extension_catalog_output}")

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


def collect_extensions(args, config):
    sources = config.get("extension_sources", [])
    selected = set(args.sources or [])
    unknown = selected - {source["id"] for source in sources}
    if unknown:
        raise SystemExit(f"Unknown extension sources: {', '.join(sorted(unknown))}")
    sources = [source for source in sources if source.get("enabled", True) or source["id"] in selected]
    source_cache = SourceCache(args.cache_dir, args.source_manifest, args.timeout)
    started_at = utc_now()
    results = collect_extension_sources(sources, source_cache, args.output_dir, source_cache.generated_at)
    for result in results:
        if result["status"] == "failed":
            print(f"Failed {result['source_id']}: {result['error']}")
        else:
            print(f"Collected {result['source_id']}: {result['artifact_count']} artifacts")
    status_results = [
        {
            "source_id": result["source_id"],
            "status": result["status"],
            "error": result["error"],
            **({"details": result["details"]} if result.get("details") else {}),
        }
        for result in results
    ]
    write_status("external", started_at, status_results, args.status_output)
    print(f"Wrote {args.status_output}")
    document = rebuild_extension_catalog_from_sources(
        args.output_dir,
        args.catalog_output,
        source_cache.generated_at,
        read_json,
        history_path=args.history_output,
    )
    validate_extension_catalog(document)
    print(f"Wrote {args.catalog_output}")
    source_cache.write_manifest()
    print(f"Wrote {args.source_manifest}")
    return all(result["status"] == "passed" for result in results)


def normalize_extensions(args, config):
    source_reader = CachedSourceReader(args.cache_dir, args.source_manifest)
    sources = config.get("extension_sources", [])
    urls = [source["url"] for source in sources if source.get("enabled", True)]
    observed_at = source_reader.latest_observed_at(urls)
    document = rebuild_extension_catalog_from_sources(
        args.output_dir,
        args.catalog_output,
        observed_at,
        read_json,
        history_path=args.history_output,
    )
    validate_extension_catalog(document)
    print(f"Wrote {args.catalog_output}")
    return True


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
        legacy_sources = dict(legacy.get("sources", {}))
        legacy_sources[legacy_source["id"]] = legacy_source
        history = merge_history(
            read_json(history_path),
            legacy_candidates,
            legacy_sources,
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
        documentation = read_json(getattr(args, "documentation_output", "data/documentation.json")) or {}
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
                build_legacy_linux_candidates(legacy_linux, documentation.get("framework_compatibility", [])),
                {"legacy-linux-artifacts": legacy_linux_source},
                observed_at,
                {"legacy-linux-artifacts"},
            )
            classify_legacy_linux_framework(history, documentation.get("framework_compatibility", []))
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
    history = migrate_history(history)
    validate_history(history)
    write_json(history, args.history_output)
    validate_legacy_windows(legacy)
    validate_compatibility_matrix(matrix)
    validate_version_history(version_history)
    snapshot_paths, _ = load_package_snapshots(args.output_dir)
    framework_path, components_path, extension_path = auxiliary_paths(args)
    framework_history = read_json(framework_path) or {"schema_version": 1, "generated_at": history["generated_at"], "sources": {}, "candidates": []}
    sdk_components = read_json(components_path) or {"schema_version": 1, "generated_at": history["generated_at"], "components": []}
    extension_history = read_json(extension_path) or {"schema_version": 1, "generated_at": history["generated_at"], "sources": {}, "extensions": []}
    extension_catalog_output = getattr(args, "extension_catalog_output", None)
    if extension_catalog_output is None:
        extension_catalog_output = str(Path(args.output_dir).parent / "extensions" / "catalog.json")
    extension_catalog = read_json(extension_catalog_output) or {"schema_version": 1, "generated_at": history["generated_at"], "sources": {}, "extensions": []}

    write_rendered_document(snapshot_paths, args.docs_output)
    write_history_document(history, args.history_docs_output)
    write_compatibility_document(matrix, args.matrix_docs_output)
    legacy_path = Path(args.legacy_docs_output)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(legacy_path, render_legacy_windows(legacy))
    legacy_linux = read_json(args.legacy_linux_output)
    if legacy_linux is not None:
        legacy_linux_path = Path(args.legacy_linux_docs_output)
        legacy_linux_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(legacy_linux_path, render_legacy_linux(legacy_linux))
    version_history_path = Path(args.version_history_docs_output)
    version_history_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(version_history_path, render_version_history(version_history))
    atomic_write_text("docs/generated/framework-history.md", render_framework_history(framework_history))
    atomic_write_text("docs/generated/sdk-components.md", render_sdk_components(sdk_components))
    atomic_write_text("docs/generated/extension-history.md", render_extension_history(extension_history))
    atomic_write_text("docs/generated/extension-catalog.md", render_extension_catalog(extension_catalog))
    validate_extension_catalog(extension_catalog)
    paths = (args.docs_output, args.history_docs_output, args.matrix_docs_output, args.legacy_docs_output, args.version_history_docs_output, "docs/generated/framework-history.md", "docs/generated/sdk-components.md", "docs/generated/extension-history.md", "docs/generated/extension-catalog.md")
    if legacy_linux is not None:
        paths += (args.legacy_linux_docs_output,)
    for path in paths:
        print(f"Wrote {path}")


def build_outputs(args):
    integrate_outputs(args)
    snapshot_paths = sorted(Path(args.output_dir).glob("*.json"))
    snapshot_times = [read_required_json(path)["last_observed_at"] for path in snapshot_paths]
    observed_at = max(snapshot_times) if snapshot_times else utc_now()
    framework_path, components_path, extension_path = auxiliary_paths(args)
    rebuild_auxiliary_outputs(args.output_dir, framework_path, components_path, observed_at, read_json, write_json)
    rebuild_extension_history(args.output_dir, extension_path, observed_at, read_json, write_json, read_json(args.history_output))
    extension_catalog_output = getattr(args, "extension_catalog_output", None)
    if extension_catalog_output is None:
        extension_catalog_output = str(Path(args.output_dir).parent / "extensions" / "catalog.json")
    extension_catalog = rebuild_extension_catalog(
        args.output_dir,
        extension_catalog_output,
        observed_at,
        read_json,
        extension_snapshot_dir=Path(extension_catalog_output).parent / "snapshots",
        history_path=Path(extension_catalog_output).parent / "history.json",
    )
    validate_extension_catalog(extension_catalog)
    history = read_json(args.history_output)
    ci_evidence = read_json(args.ci_evidence_output)
    documentation = read_json(args.documentation_output)
    if history is not None:
        history = migrate_history(history)
    if history is not None and documentation is not None:
        attach_therock_documentation_evidence(history, documentation)
    if history is not None and ci_evidence is not None:
        attach_therock_ci_evidence(history, ci_evidence)
    if history is not None:
        validate_history(history)
        write_json(history, args.history_output)
        print(f"Updated {args.history_output} with normalized evidence")
    render_outputs(args)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "runtime":
        from .runtime import main as runtime_main
        runtime_args = ["--output", args.output, "--history", args.history]
        if args.candidate_id:
            runtime_args += ["--candidate-id", args.candidate_id]
        if args.gfx:
            runtime_args += ["--gfx", args.gfx]
        runtime_main(runtime_args)
        return
    if args.command == "hardware":
        from .hardware import main as hardware_main
        hardware_args = ["--output", args.output, "--history", args.history]
        if args.candidate_id:
            hardware_args += ["--candidate-id", args.candidate_id]
        if args.gfx:
            hardware_args += ["--gfx", args.gfx]
        hardware_main(hardware_args)
        return
    if args.command == "build":
        build_outputs(args)
        return
    if args.command == "catalog":
        print(f"Wrote {write_catalog(args.root, args.output)}")
        return
    if args.command == "check":
        from .check import run_check
        run_check(args.root)
        return
    if args.command == "integrate":
        integrate_outputs(args)
        return
    if args.command == "render":
        render_outputs(args)
        return
    config = load_config(args.config)
    if args.command == "collect":
        if args.family == "therock":
            success = collect_therock(args, config)
        elif args.family == "extensions":
            success = collect_extensions(args, config)
        else:
            success = collect_legacy(args, config)
    else:
        if args.family == "therock":
            success = normalize_therock(args, config)
        elif args.family == "extensions":
            success = normalize_extensions(args, config)
        else:
            success = normalize_legacy(args, config)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
