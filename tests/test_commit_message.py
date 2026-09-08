import unittest

from scripts.check_commit_message import validate_message


class CommitMessageTests(unittest.TestCase):
    def test_accepts_real_line_breaks(self):
        message = "refactor: simplify catalog\n\n- Remove stale source entries\n- Keep current package indexes\n"

        self.assertIsNone(validate_message(message))

    def test_rejects_escaped_line_breaks(self):
        message = "refactor: simplify catalog\n\n- Remove stale source entries\\n- Keep current package indexes\n"

        self.assertEqual(
            validate_message(message),
            "commit message must use real line breaks, not escaped \\n or \\r",
        )


if __name__ == "__main__":
    unittest.main()
