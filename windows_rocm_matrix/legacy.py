import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from .documentation import parse_html_tables
from .simple_index import normalize_package_name, parse_links, version_key
from .source_adapter import run_source_adapter


STATUS = {"✅": "supported", "⚠️": "deprecated", "⚠": "deprecated", "❌": "unsupported"}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def table_headers(table):
    if not table["rows"]:
        return []
    return [cell["text"] for cell in table["rows"][0]["cells"]]


def status_value(value):
    for symbol, status in STATUS.items():
        if symbol in value:
            return status
    return "unknown"


def parse_hip_sdk_release_versions(html, source_id):
    releases = []
    for table in parse_html_tables(html):
        headers = table_headers(table)
        if headers[:3] != ["ROCm version", "Linux support", "Windows support"]:
            continue
        for row in table["rows"][1:]:
            cells = [cell["text"] for cell in row["cells"]]
            if len(cells) < 3 or not re.fullmatch(r"\d+\.\d+", cells[0]):
                continue
            releases.append(
                {
                    "rocm_series": cells[0],
                    "linux_support": status_value(cells[1]) == "supported",
                    "windows_support": status_value(cells[2]) == "supported",
                    "source_id": source_id,
                }
            )
    if not releases:
        raise ValueError("Could not find HIP SDK release versioning table")
    return sorted(releases, key=lambda item: version_key(item["rocm_series"]))


def parse_hip_sdk_gpu_support(html, rocm_series, source_id):
    products = []
    for table in parse_html_tables(html):
        headers = table_headers(table)
        required = ["Name", "Architecture", "LLVM target", "Runtime", "HIP SDK"]
        if headers[:5] != required:
            continue
        for row in table["rows"][1:]:
            cells = [cell["text"] for cell in row["cells"]]
            if len(cells) < 5 or not re.fullmatch(r"gfx[0-9a-z]+", cells[2].lower()):
                continue
            products.append(
                {
                    "rocm_series": rocm_series,
                    "product": cells[0],
                    "architecture": cells[1],
                    "gfx": cells[2].lower(),
                    "runtime_status": status_value(cells[3]),
                    "hip_sdk_status": status_value(cells[4]),
                    "source_id": source_id,
                }
            )
    if not products:
        raise ValueError(f"Could not find HIP SDK GPU support table for {rocm_series}")
    return sorted(products, key=lambda item: (version_key(item["rocm_series"]), item["gfx"], item["product"]))


def split_products(value):
    return [item.strip() for item in re.split(r"(?=AMD\s)", value) if item.strip()]


def parse_pytorch_windows_support(html, product_family, source_id):
    release = {"product_family": product_family, "source_id": source_id}
    for table in parse_html_tables(html):
        headers = table_headers(table)
        if headers[:3] == ["ROCm Version", "Supported Architectures", "Supported AMD Radeon™ Hardware"]:
            row = table["rows"][1] if len(table["rows"]) > 1 else None
            if row and len(row["cells"]) >= 3:
                cells = [cell["text"] for cell in row["cells"]]
                version_match = re.search(r"\d+(?:\.\d+)+", cells[0])
                if version_match:
                    release["rocm_version"] = version_match.group(0)
                    release["gfx_targets"] = sorted(set(re.findall(r"gfx(?:\d{4}|\d{3}[a-z]?|\d{2}[a-z])", cells[1].lower())))
                    release["products"] = split_products(cells[2])
        if headers[:4] == ["PyTorch Version", "ROCm Version", "Python Version", "Comments"]:
            row = table["rows"][1] if len(table["rows"]) > 1 else None
            if row and len(row["cells"]) >= 4:
                cells = [cell["text"] for cell in row["cells"]]
                release["torch_version"] = cells[0]
                release["python_versions"] = sorted(set(re.findall(r"\d+\.\d+", cells[2])))
                release["comments"] = cells[3]
    required = {"rocm_version", "gfx_targets", "products", "torch_version", "python_versions"}
    if not required.issubset(release):
        raise ValueError(f"Could not find Windows PyTorch support matrices in {source_id}")
    return release


def parse_legacy_artifact(filename, url):
    if filename.lower().endswith(".whl"):
        parts = filename[:-4].split("-")
        if len(parts) < 5:
            return None
        return {
            "package": normalize_package_name(parts[0]),
            "version": parts[1],
            "filename": filename,
            "python_tag": parts[-3],
            "abi_tag": parts[-2],
            "platform_tag": parts[-1],
            "url": url,
        }
    if filename.lower().endswith(".tar.gz"):
        name, separator, version = filename[:-7].rpartition("-")
        if not separator:
            return None
        return {
            "package": normalize_package_name(name),
            "version": version,
            "filename": filename,
            "python_tag": "source",
            "abi_tag": "source",
            "platform_tag": "source",
            "url": url,
        }
    return None


def artifact_links(html, base_url):
    artifacts = []
    subindexes = []
    for url, text in parse_links(html, base_url):
        filename = unquote(PurePosixPath(urlparse(url).path).name)
        artifact = parse_legacy_artifact(filename, url)
        if artifact:
            artifacts.append(artifact)
        elif url.rstrip("/") != base_url.rstrip("/") and url.endswith("/") and normalize_package_name(filename) in {"torch", "torchvision", "torchaudio"}:
            subindexes.append(url)
    return artifacts, sorted(set(subindexes))


def collect_artifact_releases(source, fetch_text):
    root_html = fetch_text(source["url"])
    releases = []
    for url, text in parse_links(root_html, source["url"]):
        match = re.search(r"/rocm-rel-([^/]+)/$", url)
        if not match:
            continue
        artifacts, subindexes = artifact_links(fetch_text(url), url)
        for subindex in subindexes:
            nested, ignored = artifact_links(fetch_text(subindex), subindex)
            artifacts.extend(nested)
        releases.append(
            {
                "release_id": match.group(1),
                "url": url,
                "artifacts": sorted(artifacts, key=lambda item: (item["package"], version_key(item["version"]), item["filename"])),
                "source_id": source["id"],
            }
        )
    return sorted(releases, key=lambda item: version_key(item["release_id"]))


def collect_legacy_windows_sources(config, fetch_text, existing=None, observed_at=None):
    observed_at = observed_at or utc_now()
    existing = existing or {
        "schema_version": 1,
        "generated_at": observed_at,
        "sources": {},
        "hip_sdk_releases": [],
        "hip_sdk_gpu_support": [],
        "pytorch_windows_support": [],
        "artifact_releases": [],
    }
    source_records = dict(existing.get("sources", {}))
    collections = {
        "hip_sdk_releases": list(existing.get("hip_sdk_releases", [])),
        "hip_sdk_gpu_support": list(existing.get("hip_sdk_gpu_support", [])),
        "pytorch_windows_support": list(existing.get("pytorch_windows_support", [])),
        "artifact_releases": list(existing.get("artifact_releases", [])),
    }
    results = []
    passed = False

    def run(source, collection_name, collect):
        nonlocal passed
        items, result = run_source_adapter(source, collect, observed_at)
        results.append(result)
        if items is None:
            return
        passed = True
        collections[collection_name] = [item for item in collections[collection_name] if item["source_id"] != source["id"]]
        collections[collection_name].extend(items)
        source_records[source["id"]] = {**source, "observed_at": observed_at}

    release_source = config["hip_sdk_release_versions"]
    run(
        release_source,
        "hip_sdk_releases",
        lambda: parse_hip_sdk_release_versions(fetch_text(release_source["url"]), release_source["id"]),
    )

    for source in config["hip_sdk_gpu_support"]:
        run(
            source,
            "hip_sdk_gpu_support",
            lambda source=source: parse_hip_sdk_gpu_support(fetch_text(source["url"]), source["rocm_series"], source["id"]),
        )

    for source in config["pytorch_windows_support"]:
        run(
            source,
            "pytorch_windows_support",
            lambda source=source: [parse_pytorch_windows_support(fetch_text(source["url"]), source["product_family"], source["id"])],
        )

    artifact_source = config["artifact_index"]
    run(artifact_source, "artifact_releases", lambda: collect_artifact_releases(artifact_source, fetch_text))

    document = {
        "schema_version": 1,
        "generated_at": observed_at if passed else existing["generated_at"],
        "sources": {key: source_records[key] for key in sorted(source_records)},
        "hip_sdk_releases": sorted(collections["hip_sdk_releases"], key=lambda item: version_key(item["rocm_series"])),
        "hip_sdk_gpu_support": sorted(collections["hip_sdk_gpu_support"], key=lambda item: (version_key(item["rocm_series"]), item["gfx"], item["product"])),
        "pytorch_windows_support": sorted(collections["pytorch_windows_support"], key=lambda item: (version_key(item["rocm_version"]), item["product_family"])),
        "artifact_releases": sorted(collections["artifact_releases"], key=lambda item: version_key(item["release_id"])),
    }
    return document, results


def collect_legacy_windows(config, fetch_text):
    document, results = collect_legacy_windows_sources(config, fetch_text)
    failures = [result for result in results if result["status"] == "failed"]
    if failures:
        raise ValueError("Legacy source collection failed: " + ", ".join(result["source_id"] for result in failures))
    return document


def build_legacy_candidates(document):
    """Convert direct legacy wheels into the common historical candidate shape."""
    support_by_version = {}
    for item in document.get("pytorch_windows_support", []):
        support_by_version.setdefault(item["rocm_version"], set()).update(item.get("gfx_targets", []))

    candidates = []
    for release in document.get("artifact_releases", []):
        artifacts = [item for item in release["artifacts"] if item["filename"].lower().endswith(".whl")]
        by_package = {}
        for artifact in artifacts:
            by_package.setdefault(artifact["package"], []).append(artifact)
        required = {"torch", "torchvision", "torchaudio"}
        if not required.issubset(by_package) or release["release_id"] not in support_by_version:
            continue
        torch = sorted(by_package["torch"], key=lambda item: item["version"])[-1]
        vision = sorted(by_package["torchvision"], key=lambda item: item["version"])[-1]
        audio = sorted(by_package["torchaudio"], key=lambda item: item["version"])[-1]
        python_tags = sorted({torch["python_tag"], vision["python_tag"], audio["python_tag"]})
        if not all(tag.startswith("cp") for tag in python_tags):
            continue
        candidates.append(
            {
                "id": ":".join(("legacy", "stable", release["release_id"], torch["version"], vision["version"], audio["version"], ",".join(python_tags))),
                "distribution_family": "legacy",
                "platform": "windows",
                "channel": "stable",
                "rocm_version": release["release_id"],
                "hip_version": None,
                "evidence_status": {"artifact": "artifact_available", "resolver": "not_collected", "runtime": "not_collected", "hardware": "not_collected"},
                "torch_version": torch["version"],
                "torchvision_version": vision["version"],
                "torchaudio_version": audio["version"],
                "python_tags": python_tags,
                "gfx_targets": sorted(support_by_version[release["release_id"]]),
                "source_id": "legacy-artifacts",
                "wheel_urls": [item["url"] for item in artifacts],
            }
        )
    return candidates


def render_legacy_windows(document):
    artifact_releases = {item["release_id"]: item for item in document.get("artifact_releases", [])}
    documented_releases = {
        item["rocm_version"] for item in document.get("pytorch_windows_support", [])
    }
    documented_releases.update(item["rocm_series"] for item in document.get("hip_sdk_releases", []))
    release_ids = sorted(
        set(artifact_releases) | documented_releases,
        key=version_key,
        reverse=True,
    )
    lines = [
        "<!-- Generated by windows_rocm_matrix.collect. Do not edit manually. -->",
        "",
        "# Legacy Windows ROCm evidence",
        "",
        "HIP SDK documentation, PyTorch support documentation, and repository artifacts are independent evidence. A row in one section does not imply support in another.",
        "",
        "## Coverage summary",
        "",
        "| ROCm release | Artifacts | Platform support evidence | Runtime verification |",
        "| --- | ---: | --- | --- |",
    ]
    for release_id in release_ids:
        artifact_count = len(artifact_releases.get(release_id, {}).get("artifacts", []))
        support = "documented" if release_id in documented_releases else "not collected"
        lines.append(f"| `{release_id}` | {artifact_count} | {support} | not collected |")
    lines.extend([
        "",
        "`documented` means that a Windows support statement or product mapping was observed. It does not establish resolver, runtime, or hardware success.",
        "",
        "## HIP SDK release history",
        "",
        "| ROCm series | Windows HIP SDK |",
        "| --- | --- |",
    ])
    for release in sorted(document["hip_sdk_releases"], key=lambda item: version_key(item["rocm_series"]), reverse=True):
        lines.append(f"| `{release['rocm_series']}` | {'Yes' if release['windows_support'] else 'No'} |")
    lines.extend(["", "## Versioned HIP SDK GPU documentation", "", "| ROCm series | Products documented | Runtime supported | HIP SDK supported |", "| --- | ---: | ---: | ---: |"])
    by_series = {}
    for product in document["hip_sdk_gpu_support"]:
        group = by_series.setdefault(product["rocm_series"], [])
        group.append(product)
    for series, products in sorted(by_series.items(), key=lambda item: version_key(item[0]), reverse=True):
        lines.append(f"| `{series}` | {len(products)} | {sum(item['runtime_status'] == 'supported' for item in products)} | {sum(item['hip_sdk_status'] == 'supported' for item in products)} |")
    lines.extend(["", "## PyTorch on Windows documentation", "", "| ROCm | Product family | Torch | Python | GFX targets |", "| --- | --- | --- | --- | --- |"])
    for release in sorted(document["pytorch_windows_support"], key=lambda item: version_key(item["rocm_version"]), reverse=True):
        lines.append(f"| `{release['rocm_version']}` | {release['product_family']} | `{release['torch_version']}` | {', '.join(release['python_versions'])} | {', '.join(f'`{gfx}`' for gfx in release['gfx_targets'])} |")
    lines.extend(["", "## Legacy package repositories", "", "| Repository release | Artifacts | Packages |", "| --- | ---: | --- |"])
    for release in sorted(document["artifact_releases"], key=lambda item: version_key(item["release_id"]), reverse=True):
        packages = sorted({item["package"] for item in release["artifacts"]})
        lines.append(f"| `{release['release_id']}` | {len(release['artifacts'])} | {', '.join(f'`{name}`' for name in packages)} |")
    return "\n".join(lines).rstrip() + "\n"
