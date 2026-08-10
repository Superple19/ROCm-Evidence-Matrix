import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

from packaging.version import InvalidVersion, Version

PACKAGE_SEPARATOR = re.compile(r"[-_.]+")
DEVICE_PACKAGE_PREFIXES = (
    "rocm-sdk-device-",
    "amd-torch-device-",
    "amd-torchvision-device-",
)


def gfx_key(gfx):
    match = re.fullmatch(r"gfx(\d+)([a-z]*)", gfx.lower())
    if not match:
        return (-1, "", gfx.lower())
    digits, suffix = match.groups()
    numeric = int(digits)
    if suffix:
        numeric = numeric * 10 + int(suffix, 36)
    return (numeric, gfx.lower())


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append((self._href, "".join(self._text).strip()))
        self._href = None
        self._text = []


def parse_links(html, base_url):
    parser = AnchorParser()
    parser.feed(html)
    return [(urljoin(base_url, href), text) for href, text in parser.links]


def normalize_package_name(name):
    return PACKAGE_SEPARATOR.sub("-", name).lower().strip("-")


def discover_packages(html, base_url):
    packages = set()
    for url, text in parse_links(html, base_url):
        candidate = text or PurePosixPath(urlparse(url).path.rstrip("/")).name
        candidate = unquote(candidate).strip().rstrip("/")
        if candidate:
            packages.add(normalize_package_name(candidate))
    return sorted(packages)


def discover_gfx_targets(package_names):
    prefix = "rocm-sdk-device-"
    return sorted(name[len(prefix):] for name in package_names if name.startswith(prefix))


def package_names_for_target(gfx):
    return tuple(prefix + gfx for prefix in DEVICE_PACKAGE_PREFIXES)


def parse_windows_wheels(html, base_url, package_name):
    artifacts = []
    expected_name = normalize_package_name(package_name)
    for url, text in parse_links(html, base_url):
        filename = unquote(PurePosixPath(urlparse(url).path).name)
        if not filename.lower().endswith(".whl"):
            continue
        stem = filename[:-4]
        parts = stem.split("-")
        if len(parts) < 5 or not (parts[-1].lower().startswith("win") or parts[-1].lower() == "any"):
            continue
        if normalize_package_name(parts[0]) != expected_name:
            continue
        artifacts.append(
            {
                "filename": filename,
                "version": parts[1],
                "python_tag": parts[-3],
                "abi_tag": parts[-2],
                "platform_tag": parts[-1],
                "url": url,
            }
        )
    return sorted(artifacts, key=lambda item: (version_key(item["version"]), item["filename"]))


def parse_linux_wheels(html, base_url, package_name):
    artifacts = []
    expected_name = normalize_package_name(package_name)
    for url, text in parse_links(html, base_url):
        filename = unquote(PurePosixPath(urlparse(url).path).name)
        if not filename.lower().endswith(".whl"):
            continue
        parts = filename[:-4].split("-")
        if len(parts) < 5 or not (parts[-1].lower() == "any" or any(parts[-1].lower().startswith(prefix) for prefix in ("linux", "manylinux", "musllinux"))):
            continue
        if normalize_package_name(parts[0]) != expected_name:
            continue
        artifacts.append({"filename": filename, "version": parts[1], "python_tag": parts[-3], "abi_tag": parts[-2], "platform_tag": parts[-1], "url": url})
    return sorted(artifacts, key=lambda item: (version_key(item["version"]), item["filename"]))


def parse_source_distributions(html, base_url, package_name):
    artifacts = []
    expected_name = normalize_package_name(package_name)
    for url, text in parse_links(html, base_url):
        filename = unquote(PurePosixPath(urlparse(url).path).name)
        if not filename.lower().endswith(".tar.gz"):
            continue
        name, separator, version = filename[:-7].rpartition("-")
        if not separator or normalize_package_name(name) != expected_name:
            continue
        artifacts.append(
            {
                "filename": filename,
                "version": version,
                "python_tag": "source",
                "abi_tag": "source",
                "platform_tag": "source",
                "url": url,
            }
        )
    return sorted(artifacts, key=lambda item: (version_key(item["version"]), item["filename"]))


def parse_package_artifacts(html, base_url, package_name, platform="windows"):
    wheels = parse_linux_wheels(html, base_url, package_name) if platform == "linux" else parse_windows_wheels(html, base_url, package_name)
    return sorted(
        wheels + parse_source_distributions(html, base_url, package_name),
        key=lambda item: (version_key(item["version"]), item["filename"]),
    )


def version_key(version):
    try:
        return Version(version)
    except InvalidVersion:
        return Version("0+invalid")


def latest_version(artifacts):
    if not artifacts:
        return None
    return max((artifact["version"] for artifact in artifacts), key=version_key)


def latest_artifacts(artifacts):
    version = latest_version(artifacts)
    if version is None:
        return []
    return [artifact for artifact in artifacts if artifact["version"] == version]
