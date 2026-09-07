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

    def test_catalog_excludes_ci_snapshots(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ci = root / "data" / "therock" / "ci"
            ci.mkdir(parents=True)
            payload = json.dumps({"schema_version": 1})
            (ci / "coverage.json").write_text(payload, encoding="utf-8")
            (ci / "evidence.json").write_text(payload, encoding="utf-8")

            ids = {item["id"] for item in build_catalog(root)["artifacts"]}

            self.assertNotIn("ci_coverage", ids)
            self.assertNotIn("ci_evidence", ids)

    def test_catalog_excludes_disabled_package_snapshots(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots = root / "data" / "therock" / "snapshots"
            snapshots.mkdir(parents=True)
            (snapshots / "stable.json").write_text(
                json.dumps({"schema_version": 1, "source": {"id": "stable", "enabled": True}}),
                encoding="utf-8",
            )
            (snapshots / "archive.json").write_text(
                json.dumps({"schema_version": 1, "source": {"id": "archive", "enabled": False}}),
                encoding="utf-8",
            )

            ids = {item["id"] for item in build_catalog(root)["artifacts"]}

            self.assertIn("package_snapshots:stable", ids)
            self.assertNotIn("package_snapshots:archive", ids)


if __name__ == "__main__":
    unittest.main()
