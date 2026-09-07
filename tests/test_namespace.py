import importlib
import unittest


class NamespaceTests(unittest.TestCase):
    def test_canonical_namespace_resolves_modules(self):
        new_collect = importlib.import_module("rocm_evidence_matrix.collect")

        self.assertTrue(callable(new_collect.main))


if __name__ == "__main__":
    unittest.main()
