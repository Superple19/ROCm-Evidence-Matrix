import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse


PACKAGE_SEPARATOR = re.compile(r"[-_.]+")
DEVICE_PACKAGE_PREFIXES = (
    "rocm-sdk-device-",
    "amd-torch-device-",
    "amd-torchvision-device-",
)


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


def parse_package_artifacts(html, base_url, package_name):
    return sorted(
        parse_windows_wheels(html, base_url, package_name) + parse_source_distributions(html, base_url, package_name),
        key=lambda item: (version_key(item["version"]), item["filename"]),
    )


def version_key(version):
    public, separator, local = version.partition("+")
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?(?:(?:\.|-)?(dev|post)(\d+))?", public)
    if not match:
        return ((-1,), -1, -1, (), version.lower())

    release = tuple(int(part) for part in match.group(1).split("."))
    pre_label = match.group(2)
    pre_number = int(match.group(3) or 0)
    phase_label = match.group(4)
    phase_number = int(match.group(5) or 0)
    pre_rank = {"a": 0, "b": 1, "rc": 2, None: 3}[pre_label]
    phase_rank = {"dev": -1, None: 0, "post": 1}[phase_label]
    local_parts = tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.findall(r"\d+|[a-z]+", local.lower())
    )
    return (release, pre_rank, pre_number, phase_rank, phase_number, local_parts)


def latest_version(artifacts):
    if not artifacts:
        return None
    return max((artifact["version"] for artifact in artifacts), key=version_key)


def latest_artifacts(artifacts):
    version = latest_version(artifacts)
    if version is None:
        return []
    return [artifact for artifact in artifacts if artifact["version"] == version]
