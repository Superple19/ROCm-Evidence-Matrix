import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from rocm_evidence_matrix.bundle import BundleError, build_bundle, verify_bundle


class BundleTests(unittest.TestCase):
    def _root(self, directory):
        root = Path(directory)
        artifacts = [
            ("compatibility_matrix", "data/matrix.json"),
            ("package_history", "data/history.json"),
            ("extension_catalog", "data/extensions/catalog.json"),
            ("comfyui_profile", "profiles/comfyui/profile.json"),
        ]
        catalog = {
            "schema_version": 1,
            "artifacts": [{"id": artifact_id, "path": path, "schema_version": 1} for artifact_id, path in artifacts],
        }
        (root / "data" / "extensions").mkdir(parents=True)
        (root / "profiles" / "comfyui").mkdir(parents=True)
        (root / "schemas").mkdir()
        (root / "data" / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        for _, path in artifacts:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"schema_version": 1, "path": path}), encoding="utf-8")
        for name in (
            "compatibility-matrix.schema.json",
            "history.schema.json",
            "extension-catalog.schema.json",
            "profile.schema.json",
        ):
            (root / "schemas" / name).write_text('{"type": "object"}', encoding="utf-8")
        schema = Path(__file__).resolve().parents[1] / "schemas" / "catalog-bundle.schema.json"
        (root / "schemas" / schema.name).write_bytes(schema.read_bytes())
        return root

    def _bundle(self, root, output):
        return build_bundle(
            root,
            output,
            bundle_version="2026.09.07",
            matrix_commit="a" * 40,
            generated_at="2026-09-07T00:00:00Z",
        )

    def _rewrite(self, source, destination, transform):
        with (
            zipfile.ZipFile(source) as original,
            zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as rewritten,
        ):
            for name in original.namelist():
                content = original.read(name)
                if name == "manifest.json":
                    manifest = json.loads(content)
                    content = (json.dumps(transform(manifest), sort_keys=True, separators=(",", ":")) + "\n").encode()
                rewritten.writestr(name, content)

    def test_bundle_is_deterministic_and_verifies_digests(self):
        with TemporaryDirectory() as directory:
            root = self._root(directory)
            first = self._bundle(root, root / "first.zip")
            second = self._bundle(root, root / "second.zip")

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(verify_bundle(first)["contract_version"], 1)

    def test_bundle_rejects_digest_mismatch(self):
        with TemporaryDirectory() as directory:
            root = self._root(directory)
            bundle = self._bundle(root, root / "bundle.zip")
            broken = root / "broken.zip"
            with zipfile.ZipFile(bundle) as original, zipfile.ZipFile(broken, "w") as rewritten:
                for name in original.namelist():
                    rewritten.writestr(name, b"tampered" if name == "data/matrix.json" else original.read(name))

            with self.assertRaises(BundleError):
                verify_bundle(broken)

    def test_bundle_rejects_path_traversal(self):
        with TemporaryDirectory() as directory:
            root = self._root(directory)
            bundle = self._bundle(root, root / "bundle.zip")
            broken = root / "broken.zip"

            def add_traversal(manifest):
                manifest["artifacts"][0]["path"] = "../escape.json"
                return manifest

            self._rewrite(bundle, broken, add_traversal)
            with self.assertRaises(BundleError):
                verify_bundle(broken)

    def test_bundle_rejects_unknown_contract(self):
        with TemporaryDirectory() as directory:
            root = self._root(directory)
            bundle = self._bundle(root, root / "bundle.zip")
            broken = root / "broken.zip"

            def use_unknown_contract(manifest):
                manifest["contract_version"] = 2
                return manifest

            self._rewrite(bundle, broken, use_unknown_contract)
            with self.assertRaises(BundleError):
                verify_bundle(broken)


if __name__ == "__main__":
    unittest.main()
