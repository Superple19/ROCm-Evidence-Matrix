import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser


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
            self._cell = {"header": tag == "th", "conditions": parse_conditions(attributes), "text": []}

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self._cell is not None:
            self._cell["text"] = " ".join("".join(self._cell["text"]).split())
            self._row["cells"].append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row["cells"]:
                self._table["rows"].append(self._row)
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
    rows = []
    for line in section_match.group(1).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[1] in {"LLVM target", "-----------"} or not cells[1].startswith("gfx"):
            continue
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
    return sorted(rows, key=lambda item: item["gfx"])


def collect_documentation(sources, fetch_text):
    sources_by_id = {source["id"]: source for source in sources}
    required = {"rocm-compatibility-matrix", "amd-gpu-specifications", "therock-supported-gpus"}
    missing = required - set(sources_by_id)
    if missing:
        raise ValueError(f"Missing documentation sources: {', '.join(sorted(missing))}")

    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_records = {
        source_id: {**sources_by_id[source_id], "observed_at": observed_at}
        for source_id in sorted(required)
    }
    compatibility_html = fetch_text(sources_by_id["rocm-compatibility-matrix"]["url"])
    specifications_html = fetch_text(sources_by_id["amd-gpu-specifications"]["url"])
    therock_markdown = fetch_text(sources_by_id["therock-supported-gpus"]["url"])

    return {
        "schema_version": 1,
        "last_observed_at": observed_at,
        "sources": source_records,
        "products": parse_gpu_specifications(specifications_html, "amd-gpu-specifications"),
        "windows_release_support": parse_compatibility_matrix(compatibility_html, "rocm-compatibility-matrix"),
        "therock_windows_status": parse_therock_windows_status(therock_markdown, "therock-supported-gpus"),
    }
