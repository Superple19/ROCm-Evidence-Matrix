import unittest

from rocm_evidence_matrix.extension_catalog import (
    build_extension_observations,
    merge_extension_catalog,
    merge_extension_history,
    render_extension_catalog,
)
from rocm_evidence_matrix.validation import validate_extension_catalog


OBSERVED_AT = "2026-08-08T00:00:00Z"


def snapshot(artifacts):
    return {
        "schema_version": 1,
        "last_observed_at": OBSERVED_AT,
        "source": {
            "id": "nightly",
            "distribution_family": "therock",
            "platform": "windows",
            "channel": "nightly",
            "url": "https://example.test/rocm/",
        },
        "gfx_targets": [],
        "packages": artifacts,
    }


class ExtensionCatalogTests(unittest.TestCase):
    def test_extracts_known_extension_artifacts_and_ignores_core_packages(self):
        observations = build_extension_observations(snapshot({
            "triton": [{
                "filename": "triton-3.6.0+rocm7.14.0-cp312-cp312-win_amd64.whl",
                "version": "3.6.0+rocm7.14.0",
                "python_tag": "cp312",
                "abi_tag": "cp312",
                "platform_tag": "win_amd64",
                "url": "https://example.test/triton.whl",
            }],
            "torch": [{
                "filename": "torch-2.12.0.whl",
                "version": "2.12.0",
                "python_tag": "cp312",
                "abi_tag": "cp312",
                "platform_tag": "win_amd64",
                "url": "https://example.test/torch.whl",
            }],
        }))

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["extension"], "triton")
        self.assertEqual(observations[0]["rocm_version"], "7.14.0")
        self.assertEqual(observations[0]["evidence_status"], "artifact_available")
        self.assertEqual(len(observations[0]["candidate_ids"]), 1)
        self.assertEqual(observations[0]["abi_tags"], ["cp312"])
        self.assertTrue(observations[0]["artifacts"][0]["candidate_id"].startswith("extension:triton:"))

        document = merge_extension_catalog(None, observations, OBSERVED_AT)
        document["sources"]["packages-nightly"] = {
            **snapshot({})["source"],
            "id": "packages-nightly",
            "observed_at": OBSERVED_AT,
        }
        validate_extension_catalog(document)

    def test_newer_version_is_current_and_previous_is_historical(self):
        source = snapshot({"triton": []})["source"]
        source["id"] = "stable"
        source["channel"] = "stable"

        def observe(version):
            return build_extension_observations(snapshot({"triton": [{
                "filename": f"triton-{version}-cp312-cp312-win_amd64.whl",
                "version": version,
                "python_tag": "cp312",
                "abi_tag": "cp312",
                "platform_tag": "win_amd64",
                "url": f"https://example.test/triton-{version}.whl",
            }]}))[0]

        older = observe("3.5.0")
        newer = observe("3.6.0")
        document = merge_extension_catalog(None, [older], OBSERVED_AT)
        document = merge_extension_catalog(document, [newer], OBSERVED_AT)
        self.assertEqual(
            {item["version"]: item["lifecycle"] for item in document["extensions"]},
            {"3.5.0": "historical", "3.6.0": "current"},
        )

    def test_validation_rejects_artifact_status_contradiction(self):
        item = build_extension_observations(snapshot({"triton": [{
            "filename": "triton-3.6.0-cp312-cp312-win_amd64.whl",
            "version": "3.6.0",
            "python_tag": "cp312",
            "abi_tag": "cp312",
            "platform_tag": "win_amd64",
            "url": "https://example.test/triton.whl",
        }]}))[0]
        document = merge_extension_catalog(None, [item], OBSERVED_AT)
        document["sources"]["packages-nightly"] = {
            **snapshot({})["source"],
            "id": "packages-nightly",
            "observed_at": OBSERVED_AT,
        }
        document["extensions"][0]["evidence_status"] = "unknown"
        with self.assertRaisesRegex(ValueError, "status is inconsistent"):
            validate_extension_catalog(document)

    def test_history_merge_keeps_previous_extension_versions(self):
        def observe(version):
            return build_extension_observations(snapshot({"triton": [{
                "filename": f"triton-{version}-cp312-cp312-win_amd64.whl",
                "version": version,
                "python_tag": "cp312",
                "abi_tag": "cp312",
                "platform_tag": "win_amd64",
                "url": f"https://example.test/triton-{version}.whl",
            }]}))[0]

        history = merge_extension_history(None, [observe("3.5.0")], OBSERVED_AT)
        history = merge_extension_history(history, [observe("3.6.0")], "2026-08-09T00:00:00Z")
        self.assertEqual({item["version"] for item in history["extensions"]}, {"3.5.0", "3.6.0"})
        self.assertEqual(history["generated_at"], "2026-08-09T00:00:00Z")

    def test_render_includes_abi_column_and_value(self):
        item = build_extension_observations(snapshot({"triton": [{
            "filename": "triton-3.6.0-cp312-cp312-win_amd64.whl",
            "version": "3.6.0",
            "python_tag": "cp312",
            "abi_tag": "cp312",
            "platform_tag": "win_amd64",
            "url": "https://example.test/triton.whl",
        }]}))[0]
        document = merge_extension_catalog(None, [item], OBSERVED_AT)
        rendered = render_extension_catalog(document)
        self.assertIn("| Extension | Version | Platform | Channel | Python | ABI | Wheel platform |", rendered)
        self.assertIn("| triton | 3.6.0 | windows | nightly | cp312 | cp312 | win_amd64 |", rendered)


if __name__ == "__main__":
    unittest.main()
