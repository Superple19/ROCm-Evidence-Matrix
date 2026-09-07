import importlib
import unittest


class NamespaceTests(unittest.TestCase):
    def test_canonical_namespace_resolves_modules(self):
        new_collect = importlib.import_module("rocm_evidence_matrix.collect")
        new_resolver = importlib.import_module("rocm_evidence_matrix.resolve")

        self.assertTrue(callable(new_collect.main))
        self.assertTrue(callable(new_resolver.main))


if __name__ == "__main__":
    unittest.main()
