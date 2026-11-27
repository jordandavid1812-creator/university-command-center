import unittest

from server.student_web.upload_validation import MAX_UPLOAD_BYTES, describe_size, validate_upload_metadata


class TestUploadCap(unittest.TestCase):
    def test_sizes_are_described_in_the_unit_students_see(self):
        self.assertEqual(describe_size(10 * 1024 * 1024), "10 MiB")
        self.assertEqual(describe_size(4_000_000), "4 MB")
        self.assertEqual(describe_size(4_500_000), "4.5 MB")

    def test_a_smaller_cap_is_enforced_at_the_boundary(self):
        self.assertEqual(validate_upload_metadata("notes.txt", 4_000_000, 4_000_000), ".txt")
        with self.assertRaisesRegex(ValueError, "no larger than 4 MB"):
            validate_upload_metadata("notes.txt", 4_000_001, 4_000_000)

    def test_a_cap_can_never_exceed_the_database_limit(self):
        with self.assertRaisesRegex(ValueError, "no larger than 10 MiB"):
            validate_upload_metadata("notes.txt", MAX_UPLOAD_BYTES + 1, MAX_UPLOAD_BYTES * 2)

    def test_default_is_unchanged(self):
        self.assertEqual(validate_upload_metadata("notes.pdf", MAX_UPLOAD_BYTES), ".pdf")


if __name__ == "__main__":
    unittest.main()
