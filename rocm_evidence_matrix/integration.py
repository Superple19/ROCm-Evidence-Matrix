from .simple_index import gfx_key, latest_version, package_names_for_target


def build_compatibility_matrix(documentation, package_snapshots):
    products_by_gfx = {}
    for product in documentation["products"]:
        products_by_gfx.setdefault(product["gfx"], []).append(product["name"])
    windows_evidence = documentation.get("platforms", {}).get("windows", {})
    release_by_gfx = {item["gfx"]: item for item in windows_evidence.get("release_support", documentation.get("windows_release_support", []))}
    therock_by_gfx = {item["gfx"]: item for item in windows_evidence.get("therock_status", documentation.get("therock_windows_status", []))}
    packages_by_platform = {}
    for snapshot in package_snapshots:
        source = snapshot["source"]
        packages_by_platform.setdefault(source.get("platform", "windows"), {})[source["channel"]] = snapshot

    targets = set(products_by_gfx) | set(release_by_gfx) | set(therock_by_gfx)
    for snapshot in package_snapshots:
        targets.update(item["gfx"] for item in snapshot["gfx_targets"])

    rows = []
    for gfx in sorted(targets, key=gfx_key, reverse=True):
        platform_channels = {}
        for platform, channels_by_name in sorted(packages_by_platform.items()):
            channels = {}
            for channel, snapshot in sorted(channels_by_name.items()):
                target = next((item for item in snapshot["gfx_targets"] if item["gfx"] == gfx), None)
                if target is None:
                    continue
                names = package_names_for_target(gfx)
                channels[channel] = {
                    "all_device_packages_available": target["all_device_packages_available"],
                    "rocm_device_version": latest_version(snapshot["packages"].get(names[0], [])),
                    "torch_device_version": latest_version(snapshot["packages"].get(names[1], [])),
                    "torchvision_device_version": latest_version(snapshot["packages"].get(names[2], [])),
                    "source_id": f"packages-{snapshot['source']['id']}",
                }
            platform_channels[platform] = channels
        windows_channels = platform_channels.get("windows", {})
        rows.append(
            {
                "gfx": gfx,
                "products": sorted(products_by_gfx.get(gfx, [])),
                "platforms": {
                    "windows": {
                        "release_support": release_by_gfx.get(gfx),
                        "therock_status": therock_by_gfx.get(gfx),
                        "package_channels": windows_channels,
                    },
                    **{
                        platform: {"package_channels": channels}
                        for platform, channels in platform_channels.items()
                        if platform != "windows"
                    },
                },
                "windows_release_support": release_by_gfx.get(gfx),
                "therock_windows_status": therock_by_gfx.get(gfx),
                "package_channels": windows_channels,
            }
        )

    sources = dict(documentation["sources"])
    for snapshot in package_snapshots:
        sources[f"packages-{snapshot['source']['id']}"] = {
            **snapshot["source"],
            "observed_at": snapshot["last_observed_at"],
        }
    observed_at = [snapshot["last_observed_at"] for snapshot in package_snapshots]
    observed_at.extend(source["observed_at"] for source in documentation["sources"].values())
    generated_at = max(observed_at)
    return {"schema_version": 1, "generated_at": generated_at, "sources": sources, "targets": rows}
