import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from windows_rocm_matrix.paths import THEROCK_SNAPSHOTS, first_existing


class PathTests(unittest.TestCase):
    def test_falls_back_to_legacy_path_when_namespaced_path_is_missing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old_path = root / "data" / "snapshots" / "stable.json"
            old_path.parent.mkdir(parents=True)
            old_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

            self.assertEqual(first_existing(root, THEROCK_SNAPSHOTS) / "stable.json", old_path)


if __name__ == "__main__":
    unittest.main()
