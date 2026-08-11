import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rocm_evidence_matrix.catalog import build_catalog, write_catalog


class CatalogTests(unittest.TestCase):
    def test_catalog_lists_existing_artifacts_and_dimensions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data" / "snapshots").mkdir(parents=True)
            (root / "data" / "matrix.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            (root / "data" / "snapshots" / "stable.json").write_text(
                json.dumps({"schema_version": 1, "source": {"distribution_family": "therock", "platform": "linux", "channel": "stable"}}),
                encoding="utf-8",
            )

            catalog = build_catalog(root)
            self.assertEqual(catalog["dimensions"]["platforms"], ["linux"])
            self.assertTrue(any(item["id"] == "compatibility_matrix" for item in catalog["artifacts"]))

    def test_writes_catalog(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            output = write_catalog(root)
            self.assertTrue(output.exists())

    def test_catalog_hash_is_stable_across_checkout_line_endings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            payload = b'{"schema_version": 1, "value": "line one"}\r\n'
            (root / "data" / "matrix.json").write_bytes(payload)

            catalog = build_catalog(root)

            expected = hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()
            artifact = next(item for item in catalog["artifacts"] if item["id"] == "compatibility_matrix")
            self.assertEqual(artifact["sha256"], expected)

    def test_catalog_generation_time_comes_from_artifacts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data" / "matrix.json").write_text(json.dumps({"schema_version": 1, "generated_at": "2026-08-08T00:00:00Z"}), encoding="utf-8")
            catalog = build_catalog(root)
            self.assertEqual(catalog["generated_at"], "2026-08-08T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
