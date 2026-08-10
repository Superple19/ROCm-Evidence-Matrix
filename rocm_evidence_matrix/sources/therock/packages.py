"""TheRock package-index collection adapter."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from ...history import build_history_observations
from ...simple_index import discover_gfx_targets, discover_packages, latest_artifacts, package_names_for_target, parse_package_artifacts


BASE_PACKAGES = (
    "apex",
    "rocm",
    "rocm-sdk-core",
    "rocm-sdk-libraries",
    "rocm-sdk-devel",
    "torch",
    "torchvision",
    "torchaudio",
    "triton",
    "jax-rocm7-pjrt",
    "jax-rocm7-plugin",
    "jax-rocm10-pjrt",
    "jax-rocm10-plugin",
    "rocm-bootstrap",
    "rocm-profiler",
)

DEVICE_ALIAS_PREFIXES = ("amd-torch-device-", "amd-torchvision-device-")
USER_AGENT = "rocm-evidence-matrix/0.1 (+https://github.com/Superple19/rocm-evidence-matrix)"


def fetch_text(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html, application/xhtml+xml;q=0.9"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def package_url(index_url, package_name):
    return index_url.rstrip("/") + "/" + package_name + "/"


def collect_source(source, timeout=20, workers=8, requested_gfx=(), framework_compatibility=(), fetch=None, observed_at=None):
    """Collect one TheRock package index and build its normalized observations."""
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
    alias_names = {
        name
        for name in available_packages
        if any(name.startswith(prefix) for prefix in DEVICE_ALIAS_PREFIXES)
        and (not requested_gfx or any(name.endswith(f"-{gfx}") for gfx in requested_gfx))
    }
    package_names.update(alias_names)
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
