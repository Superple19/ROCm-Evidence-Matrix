import json
import re
from pathlib import Path

from .ci import CI_STATES
from .identity import candidate_hash
from .persistence import atomic_write_json, atomic_write_text
from .simple_index import version_key
from .source_adapter import monotonic_generated_at


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
                    tag_sources = [
                        torch_tags,
                        torch_device[torch_version],
                        torchvision_versions[vision_version],
                        torchvision_device[vision_version],
                        torchaudio_versions[audio_version],
                    ]
                    python_tags = compatible_python_tags(tag_sources)
                    if not python_tags:
                        continue
                    key = (rocm_version, torch_version, vision_version, audio_version, tuple(python_tags))
                    grouped.setdefault(key, set()).add(gfx)

    observations = []
    for key, targets in grouped.items():
        rocm_version, torch_version, vision_version, audio_version, python_tags = key
        candidate_id = candidate_id_for(
            distribution_family,
            source.get("platform", "windows"),
            source["channel"],
            rocm_version,
            torch_version,
            vision_version,
            audio_version,
            python_tags,
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
                "triton_version": None,
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
    )


def initial_evidence_status():
    return {"artifact": "artifact_available", "documentation": "not_collected", "ci": "not_collected", "resolver": "not_collected", "runtime": "not_collected", "hardware": "not_collected"}


def normalize_artifact_evidence(candidate):
    evidence = candidate.setdefault("evidence_status", initial_evidence_status())
    if candidate.get("artifact_available"):
        evidence["artifact"] = "artifact_available"
    elif evidence.get("artifact") == "artifact_available":
        evidence["artifact"] = "artifact_stale" if candidate.get("last_observed_at") else "not_collected"
    return candidate


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
            validate_history(history)
            atomic_write_json(history, path)
            return True
    return False


def execution_evidence_errors(candidate, record, kind, requested_gfx=None):
    errors = []
    expected_platform = candidate.get("platform", "windows")
    observed_platform = record.get("os")
    if observed_platform and expected_platform not in {"unknown", observed_platform}:
        errors.append(f"platform mismatch: candidate={expected_platform}, observed={observed_platform}")
    if record.get("torch_version") and record["torch_version"] != candidate.get("torch_version"):
        errors.append(f"Torch mismatch: candidate={candidate.get('torch_version')}, observed={record['torch_version']}")
    expected_hash = candidate_hash(candidate, record.get("gfx"), record.get("python_tag"), record.get("platform_tag"))
    if record.get("candidate_hash") != expected_hash:
        errors.append("candidate hash does not match the observed execution identity")
    expected_rocm = candidate.get("rocm_version")
    observed_rocm = record.get("rocm_version")
    if observed_rocm != expected_rocm:
        errors.append(f"ROCm mismatch: candidate={expected_rocm}, observed={observed_rocm}")
    if record.get("result") == "passed" and not record.get("hip_version"):
        errors.append("successful evidence has no observed HIP runtime version")
    if candidate.get("hip_version") and record.get("hip_version") and candidate["hip_version"] != record["hip_version"]:
        errors.append(f"HIP mismatch: candidate={candidate['hip_version']}, observed={record['hip_version']}")

    requested = requested_gfx or record.get("gfx")
    candidate_targets = set(candidate.get("gfx_targets", []))
    observed_targets = set()
    for device in record.get("devices", []):
        if device.get("gfx"):
            observed_targets.add(device["gfx"])
    device = record.get("device")
    if device and device.get("gfx"):
        observed_targets.add(device["gfx"])
    if requested and requested not in candidate_targets:
        errors.append(f"GFX is not part of candidate support: {requested}")
    if record.get("result") == "passed":
        if candidate.get("gfx_support") != "known":
            errors.append("candidate has no authoritative GFX support mapping")
        if not candidate_targets:
            errors.append("candidate has no supported GFX targets")
        if not observed_targets:
            errors.append("successful evidence has no observed GFX target")
        elif requested and requested not in observed_targets:
            errors.append(f"observed GFX does not match requested target: {requested}")
        elif not candidate_targets.intersection(observed_targets):
            errors.append("observed GFX is outside candidate support")
        if kind == "hardware" and not record.get("correct"):
            errors.append("hardware evidence is not marked correct")
    return errors


def promote_execution_evidence(history_path, kind, record, requested_gfx=None):
    path = Path(history_path)
    history = json.loads(path.read_text(encoding="utf-8"))
    candidate_id = record.get("candidate_id")
    candidate = next((item for item in history.get("candidates", []) if item.get("id") == candidate_id), None)
    if candidate is None:
        return False, [f"unknown candidate: {candidate_id}"]
    errors = execution_evidence_errors(candidate, record, kind, requested_gfx)
    if errors:
        return False, errors
    return update_execution_evidence(path, kind, candidate_id, record["result"]), []


def attach_therock_ci_evidence(history, ci_document):
    executions = ci_document.get("executions", []) if ci_document else []
    for candidate in history.get("candidates", []):
        if candidate.get("distribution_family") != "therock" or candidate.get("platform") != "windows" or candidate.get("lifecycle") != "current":
            continue
        refs = []
        targets = set(candidate.get("gfx_targets", []))
        for execution in executions:
            execution_targets = execution.get("targets")
            observations = execution.get("observations")
            if (
                execution.get("platform") != "windows"
                or not isinstance(execution.get("id"), str)
                or not isinstance(execution_targets, list)
                or not targets.intersection(execution_targets)
                or not isinstance(observations, list)
            ):
                continue
            execution_states = [item.get("state") for item in observations if item.get("state") in CI_STATES]
            if not execution_states:
                continue
            refs.append(execution["id"])
        if not refs:
            continue
        candidate["ci_evidence_refs"] = sorted(set(refs))[-3:]
        candidate["ci_evidence_scope"] = "gfx_platform"
        status = candidate.setdefault("evidence_status", initial_evidence_status())
        latest_states = []
        for execution in executions:
            if execution.get("id") not in refs:
                continue
            observations = sorted(execution.get("observations", []), key=lambda item: item.get("observed_at") or "")
            if observations:
                latest_states.append(observations[-1].get("state"))
        if latest_states and all(state == "success" for state in latest_states):
            status["ci"] = "ci_verified"
        elif latest_states and all(state in {"failure", "cancelled", "skipped", "timed_out"} for state in latest_states):
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
            normalize_artifact_evidence(candidate)
            candidate["id"] = candidate_id(candidate)
            candidates.append(candidate)
        return {**existing, "candidates": collapse_triton_variants(candidates)}
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
        normalize_artifact_evidence(candidate)
        candidate["id"] = candidate_id(candidate)
        candidates.append(candidate)
    return {**existing, "schema_version": 2, "candidates": collapse_triton_variants(candidates)}


def collapse_triton_variants(candidates):
    grouped = {}
    preserved = []
    for candidate in candidates:
        if candidate.get("resolver_results"):
            preserved.append(candidate)
            continue
        normalized = {**candidate, "triton_version": None}
        normalized["id"] = candidate_id(normalized)
        current = grouped.get(normalized["id"])
        if current is None:
            grouped[normalized["id"]] = normalized
            continue
        current["gfx_targets"] = sorted(set(current.get("gfx_targets", [])) | set(normalized.get("gfx_targets", [])))
        current["available_gfx_targets"] = sorted(set(current.get("available_gfx_targets", [])) | set(normalized.get("available_gfx_targets", [])))
        current["artifact_available"] = bool(current["available_gfx_targets"])
        current["first_observed_at"] = min(current["first_observed_at"], normalized["first_observed_at"])
        current["last_observed_at"] = max(current["last_observed_at"], normalized["last_observed_at"])
        for kind in current.get("evidence_status", {}):
            values = (current["evidence_status"].get(kind), normalized.get("evidence_status", {}).get(kind))
            current["evidence_status"][kind] = min((value for value in values if value), key=lambda value: STATUS_ORDER.get(value, 99))
    merged_preserved = []
    for candidate in preserved:
        key = candidate_id({**candidate, "triton_version": None})
        current = grouped.get(key)
        if current is None:
            merged_preserved.append(candidate)
            continue
        current["resolver_results"] = current.get("resolver_results", []) + [
            result for result in candidate.get("resolver_results", []) if result not in current.get("resolver_results", [])
        ]
        current["evidence_status"]["resolver"] = candidate.get("evidence_status", {}).get("resolver", current["evidence_status"].get("resolver"))
    return merged_preserved + list(grouped.values())


def classify_lifecycle(candidates):
    latest = {}
    for candidate in candidates:
        candidate.setdefault("platform", "windows")
        candidate.setdefault("gfx_support", "known" if candidate.get("gfx_targets") else "unknown")
        key = (candidate["distribution_family"], candidate["platform"], candidate["channel"])
        version = version_key(candidate["rocm_version"])
        if key not in latest or version > latest[key]:
            latest[key] = version
    for candidate in candidates:
        key = (candidate["distribution_family"], candidate["platform"], candidate["channel"])
        candidate["lifecycle"] = "current" if version_key(candidate["rocm_version"]) == latest[key] else "historical"


def merge_history(existing, observations, sources, observed_at, observed_source_ids, observed_gfx_targets=None):
    existing = migrate_history(existing)
    candidates = {item["id"]: dict(item) for item in existing["candidates"]}
    gfx_scope = set(observed_gfx_targets or ())
    for candidate in candidates.values():
        if candidate["source_id"] in observed_source_ids:
            if gfx_scope and candidate.get("gfx_support") == "known":
                candidate["available_gfx_targets"] = sorted(
                    set(candidate.get("available_gfx_targets", [])) - gfx_scope
                )
                candidate["artifact_available"] = bool(candidate["available_gfx_targets"])
            else:
                candidate["artifact_available"] = False
                candidate["available_gfx_targets"] = []
            evidence = candidate.setdefault("evidence_status", initial_evidence_status())
            if not candidate["artifact_available"] and evidence.get("artifact") == "artifact_available":
                evidence["artifact"] = "artifact_stale"

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
        if gfx_scope and current.get("gfx_support") == "known":
            current["available_gfx_targets"] = sorted(
                set(current.get("available_gfx_targets", [])) | set(observation["gfx_targets"])
            )
        else:
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
        "generated_at": monotonic_generated_at(existing, observed_at),
        "sources": merged_sources,
        "candidates": sorted(candidates.values(), key=candidate_sort_key),
    }


def render_history(history):
    grouped = {}
    for candidate in history["candidates"]:
        key = (candidate["distribution_family"], candidate.get("platform", "windows"), candidate["channel"], candidate["lifecycle"], candidate["rocm_version"])
        group = grouped.setdefault(key, {"sets": 0, "gfx_support": set(), "framework": set(), "known": set(), "available": set(), "python": set(), "evidence": {"artifact": set(), "documentation": set(), "ci": set(), "resolver": set(), "runtime": set(), "hardware": set()}})
        group["sets"] += 1
        group["gfx_support"].add(candidate.get("gfx_support", "unknown"))
        group["framework"].add(candidate.get("framework_compatibility", "not_collected"))
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
        "Each row summarizes install candidates derived from official framework compatibility rules and matching platform package build identifiers. CI status is GFX/platform-scoped evidence; it does not prove this exact package candidate passed. Artifact evidence does not prove resolver, runtime, or hardware compatibility. When GFX support is unknown, artifact availability must not be interpreted as GPU support.",
        "",
        "| Distribution | Platform | Channel | Lifecycle | ROCm build | HIP build | Framework sets | GFX support | Framework compatibility | Known GFX targets | Currently available GFX targets | Artifact | Documentation | CI | Resolver | Runtime | Hardware | Python tags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for (family, platform, channel, lifecycle, rocm_version), group in sorted(
        grouped.items(), key=lambda item: version_key(item[0][4]), reverse=True
    ):
        lines.append(
            f"| {family} | {platform} | {channel} | {lifecycle} | `{rocm_version}` | not observed | {group['sets']} | {', '.join(sorted(group['gfx_support']))} | {', '.join(ordered_statuses(group['framework']))} | {len(group['known'])} | "
            f"{len(group['available'])} | {', '.join(ordered_statuses(group['evidence']['artifact']))} | {', '.join(ordered_statuses(group['evidence']['documentation']))} | {', '.join(ordered_statuses(group['evidence']['ci']))} | {', '.join(ordered_statuses(group['evidence']['resolver']))} | "
            f"{', '.join(ordered_statuses(group['evidence']['runtime']))} | {', '.join(ordered_statuses(group['evidence']['hardware']))} | "
            f"{', '.join(f'`{tag}`' for tag in sorted(group['python']))} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_history_document(history, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, render_history(history))
