import json
import re
from pathlib import Path

from .simple_index import version_key


STATUS_ORDER = {
    "artifact_stale": 0,
    "resolver_failed": 0,
    "runtime_failed": 0,
    "hardware_failed": 0,
    "partial": 1,
    "resolver_verified": 2,
    "runtime_verified": 2,
    "hardware_verified": 2,
    "documented": 3,
    "not_applicable": 4,
    "unsupported": 5,
    "unknown": 6,
    "not_collected": 7,
    "artifact_available": 8,
}


def ordered_statuses(values):
    return sorted(values, key=lambda value: (STATUS_ORDER.get(value, 99), value))


def version_series(version):
    match = re.match(r"(\d+\.\d+)", version)
    return match.group(1) if match else None


def rocm_version_from_framework(version):
    match = re.search(r"(?:^|[.+-])rocm(\d+(?:\.\d+)+(?:[a-z]+\d+)?)", version)
    return match.group(1) if match else None


def versions_by_name(artifacts):
    versions = {}
    for artifact in artifacts:
        versions.setdefault(artifact["version"], set()).add(artifact["python_tag"])
    return versions


def compatible_python_tags(package_versions):
    tag_sets = []
    for tags in package_versions:
        cpython_tags = {tag for tag in tags if re.fullmatch(r"cp\d+", tag)}
        if cpython_tags:
            tag_sets.append(cpython_tags)
    if not tag_sets:
        return []
    return sorted(set.intersection(*tag_sets))


def build_history_observations(source, gfx_targets, packages, framework_compatibility, distribution_family):
    if distribution_family not in {"therock", "legacy"}:
        raise ValueError(f"Unsupported distribution family: {distribution_family}")
    compatibility = {item["torch_series"]: item for item in framework_compatibility}
    package_versions = {name: versions_by_name(artifacts) for name, artifacts in packages.items()}
    torch_versions = package_versions.get("torch", {})
    torchvision_versions = package_versions.get("torchvision", {})
    torchaudio_versions = package_versions.get("torchaudio", {})
    triton_versions = package_versions.get("triton", {})
    torchvision_by_rocm_series = {}
    for version in torchvision_versions:
        rocm_version = rocm_version_from_framework(version)
        series = version_series(version)
        if rocm_version and series:
            torchvision_by_rocm_series.setdefault((rocm_version, series), []).append(version)
    torchaudio_by_rocm_series = {}
    for version in torchaudio_versions:
        rocm_version = rocm_version_from_framework(version)
        series = version_series(version)
        if rocm_version and series:
            torchaudio_by_rocm_series.setdefault((rocm_version, series), []).append(version)
    grouped = {}

    for gfx in gfx_targets:
        rocm_device = package_versions.get(f"rocm-sdk-device-{gfx}", {})
        torch_device = package_versions.get(f"amd-torch-device-{gfx}", {})
        torchvision_device = package_versions.get(f"amd-torchvision-device-{gfx}", {})
        for torch_version, torch_tags in torch_versions.items():
            rocm_version = rocm_version_from_framework(torch_version)
            rule = compatibility.get(version_series(torch_version))
            required_rocm_packages = ("rocm", "rocm-sdk-core", "rocm-sdk-libraries")
            rocm_packages_available = rocm_version is not None and all(
                rocm_version in package_versions.get(name, {}) for name in required_rocm_packages
            )
            if not rocm_packages_available or rule is None or rocm_version not in rocm_device or torch_version not in torch_device:
                continue
            matching_vision = [
                version for version in torchvision_by_rocm_series.get((rocm_version, rule["torchvision_series"]), [])
                if version in torchvision_device
            ]
            matching_audio = torchaudio_by_rocm_series.get((rocm_version, rule["torchaudio_series"]), [])
            for vision_version in matching_vision:
                for audio_version in matching_audio:
                    matching_triton = [version for version in triton_versions if rocm_version_from_framework(version) == rocm_version]
                    for triton_version in matching_triton or [None]:
                        tag_sources = [
                            torch_tags,
                            torch_device[torch_version],
                            torchvision_versions[vision_version],
                            torchvision_device[vision_version],
                            torchaudio_versions[audio_version],
                        ]
                        if triton_version is not None:
                            tag_sources.append(triton_versions[triton_version])
                        python_tags = compatible_python_tags(tag_sources)
                        if not python_tags:
                            continue
                        key = (rocm_version, torch_version, vision_version, audio_version, triton_version, tuple(python_tags))
                        grouped.setdefault(key, set()).add(gfx)

    observations = []
    for key, targets in grouped.items():
        rocm_version, torch_version, vision_version, audio_version, triton_version, python_tags = key
        candidate_id = candidate_id_for(
            distribution_family,
            source.get("platform", "windows"),
            source["channel"],
            rocm_version,
            torch_version,
            vision_version,
            audio_version,
            python_tags,
            triton_version,
        )
        observations.append(
            {
                "id": candidate_id,
                "distribution_family": distribution_family,
                "platform": source.get("platform", "windows"),
                "gfx_support": "known",
                "channel": source["channel"],
                "rocm_version": rocm_version,
                # HIP is a runtime-reported version; package indexes do not expose it reliably.
                "hip_version": None,
                "evidence_status": initial_evidence_status(),
                "resolver_results": [],
                "torch_version": torch_version,
                "torchvision_version": vision_version,
                "torchaudio_version": audio_version,
                "triton_version": triton_version,
                "python_tags": list(python_tags),
                "gfx_targets": sorted(targets),
                "source_id": f"packages-{source['id']}",
            }
        )
    return sorted(observations, key=candidate_sort_key)


def candidate_sort_key(candidate):
    return (
        candidate["distribution_family"],
        candidate["channel"],
        version_key(candidate["rocm_version"]),
        version_key(candidate["torch_version"]),
        version_key(candidate["torchvision_version"]),
        version_key(candidate["torchaudio_version"]),
        version_key(candidate.get("triton_version") or "0"),
    )


def initial_evidence_status():
    return {"artifact": "artifact_available", "documentation": "not_collected", "ci": "not_collected", "resolver": "not_collected", "runtime": "not_collected", "hardware": "not_collected"}


def attach_therock_documentation_evidence(history, documentation):
    statuses = documentation.get("therock_windows_status", []) if documentation else []
    by_gfx = {}
    for item in statuses:
        by_gfx.setdefault(item.get("gfx"), []).append(item)
    for candidate in history.get("candidates", []):
        if candidate.get("distribution_family") != "therock" or candidate.get("platform") != "windows":
            continue
        refs = sorted({item["source_id"] for gfx in candidate.get("gfx_targets", []) for item in by_gfx.get(gfx, []) if item.get("source_id")})
        if not refs:
            continue
        candidate["documentation_refs"] = refs
        status = candidate.setdefault("evidence_status", initial_evidence_status())
        status["documentation"] = "documented"
    return history


def update_execution_evidence(history_path, kind, candidate_id, result):
    path = Path(history_path)
    history = json.loads(path.read_text(encoding="utf-8"))
    status = f"{kind}_verified" if result == "passed" else f"{kind}_failed"
    for candidate in history.get("candidates", []):
        if candidate.get("id") == candidate_id:
            candidate.setdefault("evidence_status", initial_evidence_status())[kind] = status
            path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            return True
    return False


def attach_therock_ci_evidence(history, ci_document):
    executions = ci_document.get("executions", []) if ci_document else []
    for candidate in history.get("candidates", []):
        if candidate.get("distribution_family") != "therock" or candidate.get("platform") != "windows" or candidate.get("lifecycle") != "current":
            continue
        refs = []
        states = []
        targets = set(candidate.get("gfx_targets", []))
        for execution in executions:
            if execution.get("platform") != "windows" or not targets.intersection(execution.get("targets", [])):
                continue
            refs.append(execution["id"])
            states.extend(item.get("state") for item in execution.get("observations", []))
        if not refs:
            continue
        candidate["ci_evidence_refs"] = sorted(set(refs))[-3:]
        candidate["ci_evidence_scope"] = "gfx_platform"
        status = candidate.setdefault("evidence_status", initial_evidence_status())
        if "success" in states:
            status["ci"] = "ci_verified"
        elif states and all(state in {"failure", "cancelled", "skipped", "timed_out"} for state in states):
            status["ci"] = "ci_failed"
        else:
            status["ci"] = "partial"
    return history


def candidate_id_for(distribution_family, platform, channel, rocm_version, torch_version, torchvision_version, torchaudio_version, python_tags, triton_version=None):
    fields = [distribution_family]
    if platform != "windows":
        fields.append(platform)
    fields.extend((channel, rocm_version, torch_version, torchvision_version, torchaudio_version, ",".join(python_tags)))
    if triton_version:
        fields.append(f"triton={triton_version}")
    return ":".join(fields)


def candidate_id(candidate):
    return candidate_id_for(
        candidate["distribution_family"],
        candidate.get("platform", "windows"),
        candidate["channel"],
        candidate["rocm_version"],
        candidate["torch_version"],
        candidate["torchvision_version"],
        candidate["torchaudio_version"],
        candidate["python_tags"],
        candidate.get("triton_version"),
    )


def migrate_history(existing):
    if not existing:
        return {"sources": {}, "candidates": []}
    schema_version = existing.get("schema_version")
    if schema_version == 2:
        candidates = []
        for item in existing.get("candidates", []):
            candidate = {**item}
            candidate.setdefault("platform", "windows")
            candidate.setdefault("hip_version", None)
            candidate.setdefault("triton_version", None)
            if not isinstance(candidate.get("evidence_status"), dict):
                candidate["evidence_status"] = initial_evidence_status()
            else:
                candidate["evidence_status"] = {**initial_evidence_status(), **candidate["evidence_status"]}
            if not isinstance(candidate.get("resolver_results"), list):
                candidate["resolver_results"] = []
            candidate.setdefault("gfx_support", "known" if candidate.get("gfx_targets") else "unknown")
            candidate["id"] = candidate_id(candidate)
            candidates.append(candidate)
        return {**existing, "candidates": candidates}
    if schema_version != 1:
        raise ValueError("Unsupported history schema")
    candidates = []
    for item in existing.get("candidates", []):
        candidate = {**item, "distribution_family": "therock"}
        candidate.setdefault("platform", "windows")
        candidate.setdefault("hip_version", None)
        candidate.setdefault("triton_version", None)
        if not isinstance(candidate.get("evidence_status"), dict):
            candidate["evidence_status"] = initial_evidence_status()
        else:
            candidate["evidence_status"] = {**initial_evidence_status(), **candidate["evidence_status"]}
        if not isinstance(candidate.get("resolver_results"), list):
            candidate["resolver_results"] = []
        candidate.setdefault("gfx_support", "known" if candidate.get("gfx_targets") else "unknown")
        candidate["id"] = candidate_id(candidate)
        candidates.append(candidate)
    return {**existing, "schema_version": 2, "candidates": candidates}


def classify_lifecycle(candidates):
    latest = {}
    for candidate in candidates:
        candidate.setdefault("platform", "windows")
        candidate.setdefault("gfx_support", "known" if candidate.get("gfx_targets") else "unknown")
        key = (candidate["distribution_family"], candidate["channel"])
        version = version_key(candidate["rocm_version"])
        if key not in latest or version > latest[key]:
            latest[key] = version
    for candidate in candidates:
        key = (candidate["distribution_family"], candidate["channel"])
        candidate["lifecycle"] = "current" if version_key(candidate["rocm_version"]) == latest[key] else "historical"


def merge_history(existing, observations, sources, observed_at, observed_source_ids):
    existing = migrate_history(existing)
    candidates = {item["id"]: dict(item) for item in existing["candidates"]}
    for candidate in candidates.values():
        if candidate["source_id"] in observed_source_ids:
            candidate["artifact_available"] = False
            candidate["available_gfx_targets"] = []
            evidence = candidate.setdefault("evidence_status", initial_evidence_status())
            if evidence.get("artifact") == "artifact_available":
                evidence["artifact"] = "not_collected"

    for observation in observations:
        current = candidates.get(observation["id"])
        if current is None:
            current = {
                **observation,
                "first_observed_at": observed_at,
                "last_observed_at": observed_at,
                "artifact_available": True,
                "available_gfx_targets": observation["gfx_targets"],
            }
            candidates[observation["id"]] = current
            continue
        current["gfx_targets"] = sorted(set(current["gfx_targets"]) | set(observation["gfx_targets"]))
        current["available_gfx_targets"] = observation["gfx_targets"]
        current["python_tags"] = observation["python_tags"]
        current["last_observed_at"] = observed_at
        current["artifact_available"] = True
        current["evidence_status"] = {**initial_evidence_status(), **current.get("evidence_status", {}), "artifact": "artifact_available"}

    classify_lifecycle(candidates.values())
    merged_sources = dict(existing.get("sources", {}))
    merged_sources.update(sources)
    return {
        "schema_version": 2,
        "generated_at": observed_at,
        "sources": merged_sources,
        "candidates": sorted(candidates.values(), key=candidate_sort_key),
    }


def render_history(history):
    grouped = {}
    for candidate in history["candidates"]:
        key = (candidate["distribution_family"], candidate.get("platform", "windows"), candidate["channel"], candidate["lifecycle"], candidate["rocm_version"])
        group = grouped.setdefault(key, {"sets": 0, "known": set(), "available": set(), "python": set(), "evidence": {"artifact": set(), "documentation": set(), "ci": set(), "resolver": set(), "runtime": set(), "hardware": set()}})
        group["sets"] += 1
        group["known"].update(candidate["gfx_targets"])
        group["available"].update(candidate["available_gfx_targets"])
        group["python"].update(candidate["python_tags"])
        for name, status in candidate.get("evidence_status", initial_evidence_status()).items():
            group["evidence"].setdefault(name, set()).add(status)

    lines = [
        "<!-- Generated by windows_rocm_matrix.collect. Do not edit manually. -->",
        "",
        "# Historical package catalog",
        "",
        "Each row summarizes install candidates derived from official framework compatibility rules and matching platform package build identifiers. CI status is GFX/platform-scoped evidence; it does not prove this exact package candidate passed. Artifact evidence does not prove resolver, runtime, or hardware compatibility.",
        "",
        "| Distribution | Platform | Channel | Lifecycle | ROCm build | HIP build | Framework sets | Known GFX targets | Currently available GFX targets | Artifact | Documentation | CI | Resolver | Runtime | Hardware | Python tags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for (family, platform, channel, lifecycle, rocm_version), group in sorted(
        grouped.items(), key=lambda item: version_key(item[0][4]), reverse=True
    ):
        lines.append(
            f"| {family} | {platform} | {channel} | {lifecycle} | `{rocm_version}` | not observed | {group['sets']} | {len(group['known'])} | "
            f"{len(group['available'])} | {', '.join(ordered_statuses(group['evidence']['artifact']))} | {', '.join(ordered_statuses(group['evidence']['documentation']))} | {', '.join(ordered_statuses(group['evidence']['ci']))} | {', '.join(ordered_statuses(group['evidence']['resolver']))} | "
            f"{', '.join(ordered_statuses(group['evidence']['runtime']))} | {', '.join(ordered_statuses(group['evidence']['hardware']))} | "
            f"{', '.join(f'`{tag}`' for tag in sorted(group['python']))} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_history_document(history, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_history(history), encoding="utf-8", newline="\n")
