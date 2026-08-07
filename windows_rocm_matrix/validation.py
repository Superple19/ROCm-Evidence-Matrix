from .simple_index import package_names_for_target


def validate_snapshot(snapshot):
    if snapshot.get("schema_version") != 1:
        raise ValueError("Unsupported package snapshot schema")

    observed_at = snapshot.get("last_observed_at")
    if not isinstance(observed_at, str) or not observed_at.endswith("Z"):
        raise ValueError("last_observed_at must be a UTC timestamp")

    source = snapshot.get("source")
    if not isinstance(source, dict) or set(source) != {"id", "channel", "url"}:
        raise ValueError("source must contain id, channel, and url")
    if source["channel"] not in {"stable", "nightly", "staging"}:
        raise ValueError(f"Unsupported channel: {source['channel']}")
    if not source["url"].startswith("https://"):
        raise ValueError("source url must use HTTPS")

    packages = snapshot.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("packages must be an object")
    for package_name, artifacts in packages.items():
        if not isinstance(artifacts, list):
            raise ValueError(f"Package artifacts must be a list: {package_name}")
        versions = {artifact.get("version") for artifact in artifacts}
        if len(versions) > 1:
            raise ValueError(f"Snapshot contains multiple versions for {package_name}")
        for artifact in artifacts:
            required = {"filename", "version", "python_tag", "abi_tag", "platform_tag", "url"}
            if set(artifact) != required:
                raise ValueError(f"Invalid artifact fields for {package_name}")
            if not (artifact["platform_tag"].startswith("win") or artifact["platform_tag"] in {"any", "source"}):
                raise ValueError(f"Artifact is not applicable to Windows: {package_name}")
            if not artifact["url"].startswith("https://"):
                raise ValueError(f"Artifact URL must use HTTPS: {package_name}")

    gfx_targets = snapshot.get("gfx_targets")
    if not isinstance(gfx_targets, list):
        raise ValueError("gfx_targets must be a list")
    for target in gfx_targets:
        expected_names = list(package_names_for_target(target["gfx"]))
        if target["device_packages"] != expected_names:
            raise ValueError(f"Unexpected device package names for {target['gfx']}")
        expected_available = all(packages.get(name) for name in expected_names)
        if target["all_device_packages_available"] != expected_available:
            raise ValueError(f"Incorrect device package availability for {target['gfx']}")


def validate_documentation_snapshot(snapshot):
    if snapshot.get("schema_version") != 1:
        raise ValueError("Unsupported documentation snapshot schema")
    if not snapshot.get("last_observed_at", "").endswith("Z"):
        raise ValueError("Documentation observation time must be UTC")
    sources = snapshot.get("sources", {})
    source_ids = set(sources)
    for source in sources.values():
        required = {"id", "url", "preferred_url", "fallback_used", "observed_at"}
        if set(source) != required:
            raise ValueError(f"Invalid documentation source record: {source.get('id', 'unknown')}")
        if not source["url"].startswith("https://") or not source["preferred_url"].startswith("https://"):
            raise ValueError(f"Documentation source URLs must use HTTPS: {source['id']}")
        if not source["observed_at"].endswith("Z"):
            raise ValueError(f"Documentation source observation time must be UTC: {source['id']}")
    for collection in ("products", "windows_release_support", "therock_windows_status", "framework_compatibility"):
        if not isinstance(snapshot.get(collection), list):
            raise ValueError(f"{collection} must be a list")
        for item in snapshot[collection]:
            if item.get("source_id") not in source_ids:
                raise ValueError(f"Unknown source id in {collection}")
            if collection != "framework_compatibility" and not item.get("gfx", "").startswith("gfx"):
                raise ValueError(f"Invalid GFX target in {collection}")
    for item in snapshot["windows_release_support"]:
        if not item["windows_versions"]:
            raise ValueError(f"Missing Windows version for {item['gfx']}")


def validate_compatibility_matrix(matrix):
    if matrix.get("schema_version") != 1:
        raise ValueError("Unsupported compatibility matrix schema")
    if not matrix.get("generated_at", "").endswith("Z"):
        raise ValueError("Compatibility matrix generation time must be UTC")
    source_ids = set(matrix.get("sources", {}))
    seen = set()
    for target in matrix.get("targets", []):
        gfx = target.get("gfx")
        if not gfx or gfx in seen:
            raise ValueError("Compatibility matrix targets must have unique GFX identifiers")
        seen.add(gfx)
        support = target.get("windows_release_support")
        status = target.get("therock_windows_status")
        if support and support["source_id"] not in source_ids:
            raise ValueError(f"Unknown release support source for {gfx}")
        if status and status["source_id"] not in source_ids:
            raise ValueError(f"Unknown TheRock source for {gfx}")
        for packages in target.get("package_channels", {}).values():
            if packages["source_id"] not in source_ids:
                raise ValueError(f"Unknown package source for {gfx}")


def validate_history(history):
    if history.get("schema_version") != 1:
        raise ValueError("Unsupported history schema")
    if not history.get("generated_at", "").endswith("Z"):
        raise ValueError("History generation time must be UTC")
    source_ids = set(history.get("sources", {}))
    candidate_ids = set()
    for candidate in history.get("candidates", []):
        if candidate["id"] in candidate_ids:
            raise ValueError(f"Duplicate history candidate: {candidate['id']}")
        candidate_ids.add(candidate["id"])
        if candidate["source_id"] not in source_ids:
            raise ValueError(f"Unknown history source: {candidate['source_id']}")
        if candidate["channel"] not in {"stable", "nightly", "staging"}:
            raise ValueError(f"Unsupported history channel: {candidate['channel']}")
        if not set(candidate["available_gfx_targets"]).issubset(candidate["gfx_targets"]):
            raise ValueError(f"Available targets are not known for {candidate['id']}")
        if candidate["artifact_available"] != bool(candidate["available_gfx_targets"]):
            raise ValueError(f"Incorrect artifact availability for {candidate['id']}")
        if not candidate["python_tags"]:
            raise ValueError(f"Missing Python tags for {candidate['id']}")


def validate_resolver_verifications(document):
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported resolver verification schema")
    if not document.get("generated_at", "").endswith("Z"):
        raise ValueError("Resolver verification generation time must be UTC")
    ids = set()
    for record in document.get("verifications", []):
        if record["id"] in ids:
            raise ValueError(f"Duplicate resolver verification: {record['id']}")
        ids.add(record["id"])
        if record["result"] not in {"passed", "failed"}:
            raise ValueError(f"Invalid resolver result: {record['result']}")
        if not record["gfx"].startswith("gfx") or not record["python_tag"].startswith("cp"):
            raise ValueError(f"Invalid resolver environment: {record['id']}")
        if record["result"] == "passed" and (record["exit_code"] != 0 or not record["resolved_packages"]):
            raise ValueError(f"Passed resolver verification lacks evidence: {record['id']}")
        if record["result"] == "failed" and record["exit_code"] == 0:
            raise ValueError(f"Failed resolver verification has a successful exit code: {record['id']}")


def validate_legacy_windows(document):
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported legacy Windows schema")
    if not document.get("generated_at", "").endswith("Z"):
        raise ValueError("Legacy Windows generation time must be UTC")
    source_ids = set(document.get("sources", {}))
    for collection in ("hip_sdk_releases", "hip_sdk_gpu_support", "pytorch_windows_support", "artifact_releases"):
        if not isinstance(document.get(collection), list):
            raise ValueError(f"{collection} must be a list")
        for item in document[collection]:
            if item["source_id"] not in source_ids:
                raise ValueError(f"Unknown legacy source in {collection}: {item['source_id']}")
    for product in document["hip_sdk_gpu_support"]:
        if not product["gfx"].startswith("gfx"):
            raise ValueError(f"Invalid legacy GFX target: {product['gfx']}")
        if product["runtime_status"] not in {"supported", "deprecated", "unsupported", "unknown"}:
            raise ValueError(f"Invalid runtime status: {product['runtime_status']}")
        if product["hip_sdk_status"] not in {"supported", "deprecated", "unsupported", "unknown"}:
            raise ValueError(f"Invalid HIP SDK status: {product['hip_sdk_status']}")
    for release in document["artifact_releases"]:
        for artifact in release["artifacts"]:
            if not artifact["url"].startswith(release["url"]):
                raise ValueError(f"Artifact outside legacy release index: {artifact['url']}")


def validate_collection_status(document):
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported collection status schema")
    if document.get("distribution_family") not in {"therock", "legacy"}:
        raise ValueError("Invalid collection distribution family")
    for field in ("started_at", "completed_at"):
        if not document.get(field, "").endswith("Z"):
            raise ValueError(f"{field} must be a UTC timestamp")
    source_ids = set()
    for result in document.get("results", []):
        if result["source_id"] in source_ids:
            raise ValueError(f"Duplicate collection result: {result['source_id']}")
        source_ids.add(result["source_id"])
        if result["status"] not in {"passed", "failed"}:
            raise ValueError(f"Invalid collection result: {result['status']}")
        if result["status"] == "passed" and result["error"] is not None:
            raise ValueError(f"Passed source has an error: {result['source_id']}")
        if result["status"] == "failed" and not result["error"]:
            raise ValueError(f"Failed source lacks an error: {result['source_id']}")


def validate_source_manifest(document):
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported source manifest schema")
    if not document.get("generated_at", "").endswith("Z"):
        raise ValueError("Source manifest generation time must be UTC")
    urls = set()
    for response in document.get("responses", []):
        if response["url"] in urls:
            raise ValueError(f"Duplicate source response: {response['url']}")
        urls.add(response["url"])
        if not response["url"].startswith("https://"):
            raise ValueError(f"Source response URL must use HTTPS: {response['url']}")
        if len(response["sha256"]) != 64 or any(character not in "0123456789abcdef" for character in response["sha256"]):
            raise ValueError(f"Invalid source response hash: {response['url']}")
        if not response["observed_at"].endswith("Z"):
            raise ValueError(f"Source response observation time must be UTC: {response['url']}")
