import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from windows_rocm_matrix.check import run_check, validate_json_schema


class CheckCommandTests(unittest.TestCase):
    def test_committed_evidence_passes_check(self):
        run_check(Path(__file__).resolve().parents[1])

    def test_schema_validation_rejects_unknown_fields(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "value.json"
            path.write_text(json.dumps({"schema_version": 1, "generated_at": "2026-08-07T00:00:00Z", "unexpected": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_json_schema(json.loads(path.read_text(encoding="utf-8")), root / "schemas" / "source-manifest.schema.json")


if __name__ == "__main__":
    unittest.main()
