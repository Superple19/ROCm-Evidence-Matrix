import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from windows_rocm_matrix.persistence import atomic_write_text


class PersistenceTests(unittest.TestCase):
    def test_atomic_write_replaces_complete_content(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            atomic_write_text(path, "old")
            atomic_write_text(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "new")

    def test_atomic_write_cleans_temporary_file_on_replace_failure(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            atomic_write_text(path, "old")
            with patch("windows_rocm_matrix.persistence.os.replace", side_effect=OSError("locked")):
                with self.assertRaisesRegex(OSError, "locked"):
                    atomic_write_text(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
