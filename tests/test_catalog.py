import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from windows_rocm_matrix.catalog import build_catalog, write_catalog


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


if __name__ == "__main__":
    unittest.main()
