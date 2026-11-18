"""Class-of-degree bands: a guide the student can edit. Uses the shared checked_target rules
(0-5, at most four decimal places, never silently rounded) and the unrounded CGPA."""
import unittest
from decimal import Decimal

from academic_logic import CLASS_NAMES, DEFAULT_CLASS_BANDS, checked_bands, class_standing


class ClassBandTests(unittest.TestCase):
    def test_default_guide_is_the_common_nigerian_bands(self):
        self.assertEqual(dict(zip(CLASS_NAMES, DEFAULT_CLASS_BANDS)),
                         {"First Class": Decimal("4.50"), "Second Class Upper": Decimal("3.50"),
                          "Second Class Lower": Decimal("2.40"), "Third Class": Decimal("1.50"),
                          "Pass": Decimal("1.00")})

    def test_standing_and_gap_to_the_next_band(self):
        standing = class_standing(Decimal(34) / 9)  # 3.777...
        self.assertEqual(standing["current"]["name"], "Second Class Upper")
        self.assertEqual(standing["next"]["name"], "First Class")
        self.assertEqual(standing["gap"], Decimal("4.50") - Decimal(34) / 9)

    def test_edges_use_the_unrounded_cgpa(self):
        self.assertEqual(class_standing(Decimal("4.50"))["current"]["name"], "First Class")
        self.assertIsNone(class_standing(Decimal("4.50"))["next"])  # top band
        # 4.4999 shows as 4.50 when rounded, but it is still below the First Class band.
        self.assertEqual(class_standing(Decimal("4.4999"))["current"]["name"], "Second Class Upper")
        below = class_standing(Decimal("0.75"))
        self.assertIsNone(below["current"])
        self.assertEqual((below["next"]["name"], below["gap"]), ("Pass", Decimal("0.25")))

    def test_nothing_graded_means_no_standing(self):
        standing = class_standing(None)
        self.assertEqual([standing[key] for key in ("cgpa", "current", "next", "gap")], [None] * 4)
        self.assertEqual(len(standing["bands"]), 5)

    def test_own_bands_and_the_shared_checks(self):
        own = ("4.0", "3.0", "2.0", "1.0", "0.5")
        self.assertEqual(class_standing(Decimal("3.2"), own)["current"]["name"], "Second Class Upper")
        for bad in (("4.5", "3.5", "2.4", "1.5"), ("4.5", "3.5", "3.5", "1.5", "1"), ("5.1", "3", "2", "1", "0"),
                    ("4.5", "3.5", "2.4", "1.5", "1.00001"), ("4.5", "3.5", "2.4", "1.5", "-1"), "4.5"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                checked_bands(bad)


if __name__ == "__main__":
    unittest.main()
