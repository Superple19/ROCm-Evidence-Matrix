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
            if not artifact["platform_tag"].startswith("win"):
                raise ValueError(f"Non-Windows artifact in {package_name}")
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
