import re
from pathlib import Path

from .simple_index import version_key
from .source_adapter import monotonic_generated_at


JAX_PACKAGE_RE = re.compile(r"^(jax-rocm[^-]+)-(pjrt|plugin)$")
SDK_PACKAGE_RE = re.compile(r"^(rocm-bootstrap|rocm-profiler|rocm-sdk-.+)$")


def _rocm_version(version):
    match = re.search(r"(?:^|[.+-])rocm(\d+(?:\.\d+)+(?:[a-z]+\d+)?)", version)
    return match.group(1) if match else None


def _package_versions(artifacts):
    versions = {}
    for artifact in artifacts:
        versions.setdefault(artifact["version"], set()).add(artifact["python_tag"])
    return versions


def _compatible_jax_tags(pjrt_tags, plugin_tags):
    if "py3" in pjrt_tags:
        return sorted(plugin_tags)
    if "py3" in plugin_tags:
        return sorted(pjrt_tags)
    return sorted(pjrt_tags & plugin_tags)


def build_jax_observations(source, packages):
    grouped = {}
    for package_name, artifacts in packages.items():
        match = JAX_PACKAGE_RE.fullmatch(package_name)
        if not match:
            continue
        family, role = match.groups()
        for version, tags in _package_versions(artifacts).items():
            rocm_version = _rocm_version(version)
            if rocm_version is None:
                continue
            key = (family, rocm_version, role, version)
            grouped[key] = tags

    observations = []
    families = sorted({key[0] for key in grouped})
    for family in families:
        rocm_versions = sorted({key[1] for key in grouped if key[0] == family}, key=version_key)
        for rocm_version in rocm_versions:
            pjrt = [(version, grouped[(family, rocm_version, "pjrt", version)]) for key in grouped if key[:3] == (family, rocm_version, "pjrt") for version in [key[3]]]
            plugin = [(version, grouped[(family, rocm_version, "plugin", version)]) for key in grouped if key[:3] == (family, rocm_version, "plugin") for version in [key[3]]]
            for pjrt_version, pjrt_tags in pjrt:
                for plugin_version, plugin_tags in plugin:
                    tags = _compatible_jax_tags(pjrt_tags, plugin_tags)
                    if not tags:
                        continue
                    platform = source.get("platform", "unknown")
                    fields = ["jax", family, platform, source["channel"], rocm_version, pjrt_version, plugin_version, ",".join(tags)]
                    observations.append(
                        {
                            "id": ":".join(fields),
                            "distribution_family": source.get("distribution_family", "therock"),
                            "framework": "jax",
                            "runtime_family": family,
                            "platform": platform,
                            "channel": source["channel"],
                            "rocm_version": rocm_version,
                            "pjrt_package": f"{family}-pjrt",
                            "pjrt_version": pjrt_version,
                            "plugin_package": f"{family}-plugin",
                            "plugin_version": plugin_version,
                            "python_tags": tags,
                            "artifact_available": True,
                            "source_id": f"packages-{source['id']}",
                        }
                    )
    return observations


def merge_framework_history(existing, observations, sources, observed_at):
    existing = existing or {"schema_version": 1, "generated_at": observed_at, "sources": {}, "candidates": []}
    candidates = {item["id"]: dict(item) for item in existing.get("candidates", [])}
    for item in observations:
        current = candidates.get(item["id"])
        if current is None:
            candidates[item["id"]] = {**item, "first_observed_at": observed_at, "last_observed_at": observed_at}
        else:
            current.update({key: value for key, value in item.items() if key not in {"id", "first_observed_at"}})
            current["last_observed_at"] = max(current.get("last_observed_at", observed_at), observed_at)
    latest = {}
    for item in candidates.values():
        key = (item["distribution_family"], item["runtime_family"], item["platform"], item["channel"])
        current = latest.get(key)
        version = version_key(item["rocm_version"])
        if current is None or version > current:
            latest[key] = version
    for item in candidates.values():
        key = (item["distribution_family"], item["runtime_family"], item["platform"], item["channel"])
        item["lifecycle"] = "current" if version_key(item["rocm_version"]) == latest[key] else "historical"
    merged_sources = dict(existing.get("sources", {}))
    merged_sources.update(sources)
    return {"schema_version": 1, "generated_at": monotonic_generated_at(existing, observed_at), "sources": merged_sources, "candidates": sorted(candidates.values(), key=lambda item: (item["distribution_family"], item["runtime_family"], item["channel"], version_key(item["rocm_version"]), item["pjrt_version"], item["plugin_version"]))}


def build_sdk_components(source, packages):
    components = []
    for package_name, artifacts in packages.items():
        if not SDK_PACKAGE_RE.fullmatch(package_name):
            continue
        versions = sorted({artifact["version"] for artifact in artifacts}, key=version_key)
        tags = sorted({artifact["python_tag"] for artifact in artifacts})
        gfx = package_name.removeprefix("rocm-sdk-device-") if package_name.startswith("rocm-sdk-device-") else None
        components.append(
            {
                "id": f"{source['id']}:{package_name}",
                "distribution_family": source.get("distribution_family", "therock"),
                "platform": source.get("platform", "unknown"),
                "channel": source["channel"],
                "package_name": package_name,
                "component_kind": "device-package" if gfx else "sdk-component",
                "gfx": gfx,
                "versions": versions,
                "python_tags": tags,
                "artifact_available": bool(versions),
                "source_id": f"packages-{source['id']}",
            }
        )
    return components


def merge_sdk_components(existing, observations, observed_at):
    existing = existing or {"schema_version": 1, "generated_at": observed_at, "components": []}
    components = {item["id"]: dict(item) for item in existing.get("components", [])}
    for item in observations:
        current = {**components.get(item["id"], {}), **item}
        current["last_observed_at"] = max(current.get("last_observed_at", observed_at), observed_at)
        components[item["id"]] = current
        components[item["id"]].setdefault("first_observed_at", observed_at)
    return {"schema_version": 1, "generated_at": monotonic_generated_at(existing, observed_at), "components": sorted(components.values(), key=lambda item: (item["distribution_family"], item["platform"], item["channel"], item["package_name"]))}


def rebuild_auxiliary_outputs(output_dir, framework_history_path, sdk_components_path, observed_at, read_json, write_json):
    snapshots = [read_json(path) for path in sorted(Path(output_dir).glob("*.json"))]
    framework_observations = []
    component_observations = []
    sources = {}
    for snapshot in snapshots:
        source = snapshot["source"]
        sources[f"packages-{source['id']}"] = {**source, "observed_at": snapshot["last_observed_at"]}
        framework_observations.extend(build_jax_observations(source, snapshot["packages"]))
        component_observations.extend(build_sdk_components(source, snapshot["packages"]))
    framework_path = Path(framework_history_path)
    components_path = Path(sdk_components_path)
    framework = merge_framework_history(read_json(framework_path), framework_observations, sources, observed_at)
    components = merge_sdk_components(read_json(components_path), component_observations, observed_at)
    write_json(framework, framework_path)
    write_json(components, components_path)
    return framework, components


def render_framework_history(document):
    lines = ["<!-- Generated by rocm_evidence_matrix.collect. Do not edit manually. -->", "", "# JAX ROCm framework artifacts", "", "These are package artifacts observed in official indexes. They do not prove resolver or runtime compatibility.", "", "| Distribution | Platform | Channel | Lifecycle | ROCm | PJRT | Plugin | Python tags |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for item in document.get("candidates", []):
        lines.append(f"| {item['distribution_family']} | {item['platform']} | {item['channel']} | {item['lifecycle']} | `{item['rocm_version']}` | `{item['pjrt_version']}` | `{item['plugin_version']}` | {', '.join(f'`{tag}`' for tag in item['python_tags'])} |")
    return "\n".join(lines) + "\n"


def render_sdk_components(document):
    lines = ["<!-- Generated by rocm_evidence_matrix.collect. Do not edit manually. -->", "", "# ROCm SDK component evidence", "", "SDK components are listed separately from framework candidates; their presence does not prove a complete install set.", "", "| Distribution | Platform | Channel | Component | Kind | GFX | Versions |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in document.get("components", []):
        lines.append(f"| {item['distribution_family']} | {item['platform']} | {item['channel']} | `{item['package_name']}` | {item['component_kind']} | {item.get('gfx') or '—'} | {', '.join(f'`{version}`' for version in item['versions'])} |")
    return "\n".join(lines) + "\n"
