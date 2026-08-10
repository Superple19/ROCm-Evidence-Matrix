import importlib
import unittest


class NamespaceTests(unittest.TestCase):
    def test_new_namespace_resolves_existing_modules(self):
        new_collect = importlib.import_module("rocm_evidence_matrix.collect")
        old_collect = importlib.import_module("windows_rocm_matrix.collect")
        new_resolver = importlib.import_module("rocm_evidence_matrix.verification.resolver")

        self.assertTrue(callable(new_collect.main))
        self.assertTrue(callable(new_resolver.main))
        self.assertTrue(callable(old_collect.main))


if __name__ == "__main__":
    unittest.main()
