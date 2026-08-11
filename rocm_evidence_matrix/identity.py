import hashlib
import json
import re
import sys


def python_tag(version_info=None):
    version_info = version_info or sys.version_info
    return f"cp{version_info.major}{version_info.minor}"


def default_platform_tag(candidate):
    if candidate.get("distribution_family") == "legacy" and candidate.get("platform") == "linux":
        urls = candidate.get("wheel_urls", [])
        if any("linux_x86_64" in url for url in urls):
            return "linux_x86_64"
    return {
        "linux": "manylinux_2_28_x86_64",
        "windows": "win_amd64",
        "macos": "macosx_11_0_x86_64",
    }.get(candidate.get("platform"))


def candidate_hash(candidate, gfx, python_tag_value, platform_tag=None):
    identity = {
        "distribution_family": candidate.get("distribution_family", "therock"),
        "source_id": candidate.get("source_id"),
        "gfx": gfx,
        "python_tag": python_tag_value,
        "platform_tag": platform_tag,
        "packages": {name: candidate.get(name) for name in ("rocm_version", "torch_version", "torchvision_version", "torchaudio_version")},
        "wheel_urls": sorted(candidate.get("wheel_urls", [])),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()


def rocm_version_from_torch(torch_version):
    if not isinstance(torch_version, str):
        return None
    match = re.search(r"(?:^|[.+-])rocm(\d+(?:\.\d+)+(?:[a-z]+\d+)?)", torch_version)
    return match.group(1) if match else None
