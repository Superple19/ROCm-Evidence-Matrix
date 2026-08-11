import unittest

from rocm_evidence_matrix.community import merge_submission, submission_from_record
from rocm_evidence_matrix.validation import validate_community_evidence


class CommunityEvidenceTests(unittest.TestCase):
    def test_redacts_machine_identity_and_marks_self_reported(self):
        record = {"id": "runtime:one", "observed_at": "2026-08-08T00:00:00Z", "result": "passed", "hostname": "workstation", "path": "C:\\Users\\alice\\env", "devices": [{"gfx": "gfx1201"}]}
        submission = submission_from_record(record, "runtime", "2026-08-08T00:01:00Z")
        self.assertEqual(submission["source"], "community")
        self.assertEqual(submission["provenance"], "self-reported")
        self.assertTrue(submission["privacy_redacted"])
        self.assertNotIn("hostname", submission["record"])
        self.assertNotIn("alice", json_text(submission))

    def test_merge_is_append_only_and_deduplicated(self):
        record = {"observed_at": "2026-08-08T00:00:00Z", "result": "failed"}
        submission = submission_from_record(record, "hardware", "2026-08-08T00:01:00Z")
        document = merge_submission(None, submission)
        document = merge_submission(document, submission)
        validate_community_evidence(document)
        self.assertEqual(len(document["submissions"]), 1)

    def test_redacts_secrets_paths_and_unlisted_fields(self):
        record = {
            "observed_at": "2026-08-08T00:00:00Z", "result": "passed", "notes": "/opt/private/run.log /workspaces/alice/repo token=abc api_token=def",
            "api_token": "abc", "environment": {"ROCM_PATH": "C:\\Users\\alice\\rocm"},
            "devices": [{"gfx": "gfx1201", "name": "AMD GPU", "private_path": "C:\\Users\\alice\\x"}],
        }
        submission = submission_from_record(record, "runtime", "2026-08-08T00:01:00Z")
        encoded = json_text(submission)
        self.assertNotIn("abc", encoded)
        self.assertNotIn("alice", encoded)
        self.assertNotIn("notes", submission["record"])
        self.assertNotIn("environment", submission["record"])


def json_text(value):
    import json

    return json.dumps(value, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
