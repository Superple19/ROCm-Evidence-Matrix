from datetime import datetime, timezone

from .simple_index import latest_version, package_names_for_target


def build_compatibility_matrix(documentation, package_snapshots):
    products_by_gfx = {}
    for product in documentation["products"]:
        products_by_gfx.setdefault(product["gfx"], []).append(product["name"])
    release_by_gfx = {item["gfx"]: item for item in documentation["windows_release_support"]}
    therock_by_gfx = {item["gfx"]: item for item in documentation["therock_windows_status"]}
    packages_by_channel = {snapshot["source"]["channel"]: snapshot for snapshot in package_snapshots}

    targets = set(products_by_gfx) | set(release_by_gfx) | set(therock_by_gfx)
    for snapshot in package_snapshots:
        targets.update(item["gfx"] for item in snapshot["gfx_targets"])

    rows = []
    for gfx in sorted(targets):
        channels = {}
        for channel, snapshot in sorted(packages_by_channel.items()):
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
        rows.append(
            {
                "gfx": gfx,
                "products": sorted(products_by_gfx.get(gfx, [])),
                "windows_release_support": release_by_gfx.get(gfx),
                "therock_windows_status": therock_by_gfx.get(gfx),
                "package_channels": channels,
            }
        )

    sources = dict(documentation["sources"])
    for snapshot in package_snapshots:
        sources[f"packages-{snapshot['source']['id']}"] = {
            **snapshot["source"],
            "observed_at": snapshot["last_observed_at"],
        }
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"schema_version": 1, "generated_at": generated_at, "sources": sources, "targets": rows}
