import json
import re
from html.parser import HTMLParser

from .source_adapter import run_source_adapter, utc_now


class StructuredTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table":
            self._table = {"conditions": parse_conditions(attributes), "rows": []}
        elif self._table is not None and tag == "tr":
            self._row = {"conditions": parse_conditions(attributes), "cells": []}
        elif self._row is not None and tag in {"th", "td"}:
            self._cell = {"header": tag == "th", "conditions": parse_conditions(attributes), "text": [], "links": []}
        elif self._cell is not None and tag == "a" and attributes.get("href"):
            self._cell["links"].append(attributes["href"])

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self._cell is not None:
            cell = self._cell
            row = self._row
            if row is None:
                self._cell = None
                return
            cell["text"] = " ".join("".join(cell["text"]).split())
            row["cells"].append(cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            row = self._row
            table = self._table
            if table is None:
                self._row = None
                return
            if row["cells"]:
                table["rows"].append(row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def parse_conditions(attributes):
    value = attributes.get("data-show-cond")
    if not value:
        return {}
    conditions = json.loads(value)
    if not isinstance(conditions, dict) or not all(isinstance(values, list) for values in conditions.values()):
        raise ValueError("Invalid data-show-cond value")
    return conditions


def parse_html_tables(html):
    parser = StructuredTableParser()
    parser.feed(html)
    return parser.tables


def row_values(table):
    values = {}
    for row in table["rows"]:
        if row["cells"]:
            values[row["cells"][0]["text"]] = row
    return values


def parse_gpu_specifications(html, source_id):
    products = []
    for table in parse_html_tables(html):
        rows = table["rows"]
        if not rows:
            continue
        headers = [cell["text"] for cell in rows[0]["cells"]]
        if "Name" not in headers or "LLVM target name" not in headers or "Architecture" not in headers:
            continue
        indexes = {name: headers.index(name) for name in headers}
        for row in rows[1:]:
            cells = [cell["text"] for cell in row["cells"]]
            if len(cells) < len(headers):
                continue
            name = cells[indexes["Name"]]
            product = {
                "name": name,
                "category": product_category(name, "Graphics model" in indexes),
                "architecture": cells[indexes["Architecture"]],
                "gfx": cells[indexes["LLVM target name"]],
                "source_id": source_id,
            }
            if "Graphics model" in indexes:
                product["graphics_model"] = cells[indexes["Graphics model"]]
            products.append(product)
    if not products:
        raise ValueError("Could not find GPU specification tables")
    return sorted(products, key=lambda item: (item["gfx"], item["name"]))


def parse_rst_list_tables(rst):
    tables = []
    table = None
    row = None
    for line in rst.splitlines():
        if re.match(r"^\s*\.\. list-table::", line):
            if table:
                tables.append(table)
            table = {"name": None, "rows": []}
            row = None
            continue
        if table is None:
            continue
        name_match = re.match(r"^\s*:name:\s*(\S+)\s*$", line)
        if name_match:
            table["name"] = name_match.group(1)
            continue
        if re.match(r"^\s*\*\s*$", line):
            row = []
            table["rows"].append(row)
            continue
        cell_match = re.match(r"^\s+-(?:\s+(.*))?$", line)
        if cell_match and row is not None:
            row.append((cell_match.group(1) or "").strip())
            continue
        if re.match(r"^\s*\.\. ", line):
            tables.append(table)
            table = None
            row = None
    if table:
        tables.append(table)
    return tables


def parse_gpu_specifications_rst(rst, source_id):
    categories = {
        "instinct-arch-spec-table": "instinct",
        "radeon-pro-arch-spec-table": "radeon_pro",
        "radeon-arch-spec-table": "radeon",
        "ryzen-arch-spec-table": "apu",
    }
    products = []
    found_tables = set()
    for table in parse_rst_list_tables(rst):
        category = categories.get(table["name"])
        if category is None or not table["rows"]:
            continue
        headers = table["rows"][0]
        required = {"Name", "Architecture", "LLVM target name"}
        if not required.issubset(headers):
            raise ValueError(f"GPU specification table has unexpected headers: {table['name']}")
        indexes = {name: headers.index(name) for name in required}
        graphics_model_index = headers.index("Graphics model") if "Graphics model" in headers else None
        for cells in table["rows"][1:]:
            if len(cells) < len(headers):
                raise ValueError(f"GPU specification row has too few cells: {table['name']}")
            product = {
                "name": cells[indexes["Name"]],
                "category": category,
                "architecture": cells[indexes["Architecture"]],
                "gfx": cells[indexes["LLVM target name"]],
                "source_id": source_id,
            }
            if graphics_model_index is not None:
                product["graphics_model"] = cells[graphics_model_index]
            products.append(product)
        found_tables.add(table["name"])
    missing = set(categories) - found_tables
    if missing:
        raise ValueError(f"GPU specification RST is missing tables: {', '.join(sorted(missing))}")
    if not products:
        raise ValueError("GPU specification RST contains no products")
    return sorted(products, key=lambda item: (item["gfx"], item["name"]))


def product_category(name, is_apu):
    if is_apu or "Ryzen" in name:
        return "apu"
    if name.startswith("MI"):
        return "instinct"
    if name.startswith("Radeon RX"):
        return "radeon"
    return "radeon_pro"


def parse_compatibility_matrix(html, source_id):
    text = re.sub(r"<[^>]+>", " ", html)
    title = " ".join(text.split())
    match = re.search(r"ROCm\s+([0-9]+(?:\.[0-9]+){2})\s+compatibility matrix", title)
    if not match:
        raise ValueError("Could not determine ROCm compatibility matrix version")
    rocm_version = match.group(1)
    support = []

    for table in parse_html_tables(html):
        rows = row_values(table)
        target_row = rows.get("LLVM target")
        windows_row = rows.get("Supported Windows version")
        if target_row is None or windows_row is None:
            continue
        family = next(iter(table["conditions"].get("fam", ["unknown"])))
        windows_versions = [cell["text"] for cell in windows_row["cells"][1:] if cell["text"]]
        driver_rows = {
            "adrenalin_driver_versions": rows.get("Supported Adrenalin Driver version"),
            "windows_oem_driver_versions": rows.get("Supported Windows OEM Driver version"),
        }
        drivers = {
            key: [cell["text"] for cell in row["cells"][1:] if cell["text"]] if row else []
            for key, row in driver_rows.items()
        }
        for cell in target_row["cells"][1:]:
            gfx_matches = re.findall(r"gfx[0-9a-z]+", cell["text"].lower())
            selector_ids = sorted({value for values in cell["conditions"].values() for value in values})
            for gfx in gfx_matches:
                support.append(
                    {
                        "gfx": gfx,
                        "device_family": family,
                        "rocm_version": rocm_version,
                        "windows_versions": windows_versions,
                        "selector_ids": selector_ids,
                        **drivers,
                        "source_id": source_id,
                    }
                )
    return sorted(support, key=lambda item: item["gfx"])


def parse_therock_windows_status(markdown, source_id):
    section_match = re.search(r"^## ROCm on Windows\s*$([\s\S]*?)(?=^## |\Z)", markdown, re.MULTILINE)
    if not section_match:
        raise ValueError("Could not find TheRock Windows support section")
    expected_headers = ["Architecture", "LLVM target", "Build Passing", "Sanity Tested", "Release Ready"]
    table_started = False
    rows = []
    for line in section_match.group(1).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        if cells == expected_headers:
            table_started = True
            continue
        if not table_started or all(re.fullmatch(r"[-:]+", cell) for cell in cells):
            continue
        if len(cells) != len(expected_headers):
            raise ValueError("TheRock Windows support table has an unexpected column count")
        if not re.fullmatch(r"gfx[0-9a-z]+", cells[1]):
            raise ValueError(f"Invalid GFX target in TheRock Windows support table: {cells[1]}")
        rows.append(
            {
                "architecture": cells[0],
                "gfx": cells[1],
                "build_passing": "✅" in cells[2],
                "sanity_tested": "✅" in cells[3],
                "release_ready": "✅" in cells[4],
                "source_id": source_id,
            }
        )
    if not table_started:
        raise ValueError("TheRock Windows support table has unexpected headers")
    if not rows:
        raise ValueError("TheRock Windows support table is empty")
    return sorted(rows, key=lambda item: item["gfx"])


def parse_framework_compatibility(markdown, source_id):
    lines = markdown.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        table_line = line.lstrip("> ").strip()
        cells = [cell.strip().lower() for cell in table_line.strip("|").split("|")]
        if cells[:3] == ["torch version", "torchaudio version", "torchvision version"]:
            header_index = index
            break
    if header_index is None:
        raise ValueError("Could not find TheRock framework compatibility table")

    rows = []
    for line in lines[header_index + 2:]:
        table_line = line.lstrip("> ").strip()
        if not table_line or "|" not in table_line:
            break
        cells = [cell.strip().strip("`") for cell in table_line.strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"\d+\.\d+", cells[0]):
            break
        rows.append(
            {
                "torch_series": cells[0],
                "torchaudio_series": cells[1],
                "torchvision_series": cells[2],
                "source_id": source_id,
            }
        )
    if not rows:
        raise ValueError("TheRock framework compatibility table is empty")
    return sorted(rows, key=lambda item: tuple(int(part) for part in item["torch_series"].split(".")))


def parse_pytorch_version_compatibility(markdown, source_id):
    rows = []
    for line in markdown.splitlines():
        table_line = line.strip().strip("|")
        cells = [cell.strip() for cell in table_line.split("|")]
        if len(cells) < 4 or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", cells[0]):
            continue
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", cells[1]) or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", cells[3]):
            continue
        rows.append(
            {
                "torch_series": version_series(cells[0]),
                "torchaudio_series": version_series(cells[3]),
                "torchvision_series": version_series(cells[1]),
                "source_id": source_id,
            }
        )
    if not rows:
        raise ValueError("PyTorch version compatibility table is empty")
    return sorted(rows, key=lambda item: tuple(int(part) for part in item["torch_series"].split(".")))


def version_series(version):
    match = re.match(r"(\d+\.\d+)", version)
    if not match:
        raise ValueError(f"Invalid framework version: {version}")
    return match.group(1)


def parse_documentation_source(source, parser, parsers, fetch_text):
    try:
        return parser(fetch_text(source["url"]), source["id"]), source["url"], False
    except (OSError, ValueError) as preferred_error:
        fallback = source.get("fallback")
        if fallback is None:
            raise
        fallback_parser = parsers.get(fallback["parser"])
        if fallback_parser is None:
            raise ValueError(f"Unsupported fallback parser: {fallback['parser']}") from preferred_error
        try:
            items = fallback_parser(fetch_text(fallback["url"]), source["id"])
        except (OSError, ValueError) as fallback_error:
            raise ValueError(f"Preferred source failed: {preferred_error}; fallback failed: {fallback_error}") from fallback_error
        return items, fallback["url"], True


def collect_documentation_sources(sources, fetch_text, existing=None, observed_at=None):
    existing = existing or {
        "schema_version": 1,
        "last_observed_at": utc_now(),
        "sources": {},
        "products": [],
        "platforms": {"windows": {"release_support": [], "therock_status": []}},
        "windows_release_support": [],
        "therock_windows_status": [],
        "framework_compatibility": [],
    }
    observed_at = observed_at or utc_now()
    source_records = dict(existing.get("sources", {}))
    collections = {
        "products": list(existing.get("products", [])),
        "windows_release_support": list(existing.get("windows_release_support", [])),
        "therock_windows_status": list(existing.get("therock_windows_status", [])),
        "framework_compatibility": list(existing.get("framework_compatibility", [])),
    }
    existing_platforms = existing.get("platforms", {})
    windows_platform = existing_platforms.get("windows", {})
    collections["windows_release_support"] = list(
        windows_platform.get("release_support", collections["windows_release_support"])
    )
    collections["therock_windows_status"] = list(
        windows_platform.get("therock_status", collections["therock_windows_status"])
    )
    parsers = {
        "compatibility-html": parse_compatibility_matrix,
        "gpu-specifications-html": parse_gpu_specifications,
        "gpu-specifications-rst": parse_gpu_specifications_rst,
        "therock-status-markdown": parse_therock_windows_status,
        "framework-compatibility-markdown": parse_framework_compatibility,
        "pytorch-compatibility-markdown": parse_pytorch_version_compatibility,
    }
    adapters = {
        "rocm-compatibility-matrix": ("windows_release_support", "compatibility-html"),
        "amd-gpu-specifications": ("products", "gpu-specifications-html"),
        "therock-supported-gpus": ("therock_windows_status", "therock-status-markdown"),
        "therock-release-packaging": ("framework_compatibility", "framework-compatibility-markdown"),
        "pytorch-version-compatibility": ("framework_compatibility", "pytorch-compatibility-markdown"),
    }
    results = []
    passed = False
    for source in sources:
        if source["id"] not in adapters:
            raise ValueError(f"Unsupported documentation source adapter: {source['id']}")
        collection_name, default_parser = adapters[source["id"]]
        parser_name = source.get("parser", default_parser)
        parser = parsers.get(parser_name)
        if parser is None:
            raise ValueError(f"Unsupported documentation parser: {parser_name}")
        collected, result = run_source_adapter(
            source,
            lambda source=source, parser=parser: parse_documentation_source(source, parser, parsers, fetch_text),
            observed_at,
        )
        results.append(result)
        if collected is None:
            continue
        items, used_url, fallback_used = collected
        result["url"] = used_url
        passed = True
        collections[collection_name] = [item for item in collections[collection_name] if item["source_id"] != source["id"]]
        collections[collection_name].extend(items)
        source_records[source["id"]] = {
            "id": source["id"],
            "url": used_url,
            "preferred_url": source["url"],
            "fallback_used": fallback_used,
            "observed_at": observed_at,
        }

    framework_by_torch = {}
    priority = {"pytorch-version-compatibility": 0, "therock-release-packaging": 1}
    for item in sorted(collections["framework_compatibility"], key=lambda value: priority.get(value["source_id"], -1)):
        framework_by_torch[item["torch_series"]] = item
    return {
        "schema_version": 1,
        "last_observed_at": observed_at if passed else existing["last_observed_at"],
        "sources": {key: source_records[key] for key in sorted(source_records)},
        "products": sorted(collections["products"], key=lambda item: (item["gfx"], item["name"])),
        "platforms": {
            "windows": {
                "release_support": sorted(collections["windows_release_support"], key=lambda item: item["gfx"]),
                "therock_status": sorted(collections["therock_windows_status"], key=lambda item: item["gfx"]),
            }
        },
        "windows_release_support": sorted(collections["windows_release_support"], key=lambda item: item["gfx"]),
        "therock_windows_status": sorted(collections["therock_windows_status"], key=lambda item: item["gfx"]),
        "framework_compatibility": sorted(
            framework_by_torch.values(),
            key=lambda item: tuple(int(part) for part in item["torch_series"].split(".")),
        ),
    }, results
