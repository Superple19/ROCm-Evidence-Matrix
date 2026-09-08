import re

from .simple_index import gfx_key, latest_version, package_names_for_target


def _rocm_build(version):
    match = re.search(r"(?:rocm|rocmsdk)([0-9]+(?:\.[0-9]+)+(?:[a-z]+[0-9]+)?)", str(version or ""), re.IGNORECASE)
    return match.group(1) if match else None


def _latest_framework_version(artifacts, rocm_version):
    matching = [item for item in artifacts if _rocm_build(item.get("version")) == rocm_version]
    return latest_version(matching or artifacts)


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
        platform = source.get("platform")
        if platform not in {"windows", "linux", "macos", "unknown"}:
            raise ValueError(f"Package snapshot has no supported platform: {source.get('id', 'unknown')}")
        packages_by_platform.setdefault(platform, {})[source["channel"]] = snapshot

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
                names = target.get("device_packages") or package_names_for_target(gfx)
                rocm_name = next((name for name in names if name.startswith("rocm-sdk-device-")), None)
                torch_name = next((name for name in names if name.startswith("amd-torch-device-")), None)
                vision_name = next((name for name in names if name.startswith("amd-torchvision-device-")), None)
                rocm_device_version = latest_version(snapshot["packages"].get(rocm_name, [])) if rocm_name else None
                torch_device_version = latest_version(snapshot["packages"].get(torch_name, [])) if torch_name else None
                torchvision_device_version = latest_version(snapshot["packages"].get(vision_name, [])) if vision_name else None
                rocm_version = rocm_device_version or _rocm_build(torch_device_version)
                channels[channel] = {
                    "all_device_packages_available": target["all_device_packages_available"],
                    "rocm_device_version": rocm_device_version,
                    "torch_device_version": torch_device_version,
                    "torchvision_device_version": torchvision_device_version,
                    "torchaudio_version": _latest_framework_version(
                        snapshot["packages"].get("torchaudio", []),
                        rocm_version,
                    ),
                    "source_id": f"packages-{snapshot['source']['id']}",
                }
            platform_channels[platform] = channels
        windows_channels = platform_channels.get("windows", {})
        platform_evidence = {
            platform: {"package_channels": channels}
            for platform, channels in platform_channels.items()
        }
        row = {
            "gfx": gfx,
            "products": sorted(products_by_gfx.get(gfx, [])),
            "platforms": platform_evidence,
        }
        if "windows" in platform_channels:
            platform_evidence["windows"].update(
                {
                    "release_support": release_by_gfx.get(gfx),
                    "therock_status": therock_by_gfx.get(gfx),
                }
            )
            row.update(
                {
                    "windows_release_support": release_by_gfx.get(gfx),
                    "therock_windows_status": therock_by_gfx.get(gfx),
                    "package_channels": windows_channels,
                }
            )
        rows.append(row)

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
