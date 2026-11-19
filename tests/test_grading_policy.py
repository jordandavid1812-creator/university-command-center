"""Synthetic scales only: these fixtures do not represent a university policy."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
import unittest
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from grading_policy import GradingPolicy, LEGACY_POLICY
from academic_logic import (
    academic_summary, checked_grade, checked_target, course_breakdown,
    predicted_summary, projected_cgpa, target_plan, validate_courses,
)

FOUR = GradingPolicy("synthetic-four", "1", {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}, 4)


def record(code, grade, units=3, semester="First"):
    return dict(code=code, grade=grade, credit_units=units, semester=semester)


class PolicyDefinitionTests(unittest.TestCase):
    def test_rules_and_identity_are_immutable_copies(self):
        rules = {"A": 4, "F": 0}
        policy = GradingPolicy("synthetic", "1", rules, 4)
        rules["A"] = 2
        self.assertEqual(policy.grade_points["A"], Decimal(4))
        with self.assertRaises(TypeError):
            policy.grade_points["A"] = 3
        with self.assertRaises(FrozenInstanceError):
            policy.revision = "2"

    def test_invalid_points_and_bounds_are_rejected(self):
        for value in (True, 4.0, "4", Decimal("NaN"), Decimal("Infinity"), -1,
                      Decimal("0.12345"), 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                GradingPolicy("test", "1", {"A": value, "F": 0}, 4)
        for rules, maximum in (({}, 4), ({"a": 4, "F": 0}, 4), ({"AA": 4, "F": 0}, 4),
                               ({"A": 3, "F": 0}, 4), ({"A": 4, "F": 1}, 4),
                               ({"A": 4, "F": 0}, 0), ({"A": 4, "F": 0}, True)):
            with self.subTest(rules=rules, maximum=maximum), self.assertRaises(ValueError):
                GradingPolicy("test", "1", rules, maximum)

    def test_exact_points_validation_is_independent_of_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            policy = GradingPolicy("test", "1", {"A": Decimal("4.00000"),
                                   "B": Decimal("1.2345"), "F": 0}, 4)
            self.assertEqual(policy.grade_points["B"], Decimal("1.2345"))
            with self.assertRaises(ValueError):
                GradingPolicy("test", "1", {"A": 4, "B": Decimal("1.23456789"), "F": 0}, 4)

    def test_invalid_references_and_explicit_missing_policy_fail(self):
        for identifier in ("", "university name", "é", "x" * 65, None):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                GradingPolicy(identifier, "1", {"A": 4, "F": 0}, 4)
        for policy in (None, {}, "unknown"):
            for call in (lambda: academic_summary([], policy=policy),
                         lambda: predicted_summary([], {}, policy=policy),
                         lambda: course_breakdown([], policy=policy),
                         lambda: target_plan([], 3, 3, policy=policy),
                         lambda: projected_cgpa([], 3, 3, policy=policy)):
                with self.subTest(policy=policy), self.assertRaises(ValueError):
                    call()


class PolicyCalculationTests(unittest.TestCase):
    def test_legacy_default_matches_explicit_policy_across_all_paths(self):
        courses = [record(" a ", "a", Decimal("2.25")), record("F", "F", 1),
                   record("N", None, 7), record("A", "B"), record("BAD", "Z"),
                   record("LAST", "E", 2, "Second")]
        before = deepcopy(courses)
        calls = ((academic_summary, (courses,)), (validate_courses, (courses,)),
                 (course_breakdown, (courses,)), (target_plan, (courses, 4, 12)),
                 (projected_cgpa, (courses, 3, 12)),
                 (predicted_summary, (courses, {"A": "B", "F": "C", "N": "A", "BAD": "F", "LAST": "E"})))
        for function, args in calls:
            with self.subTest(function=function.__name__):
                self.assertEqual(function(*args), function(*args, policy=LEGACY_POLICY))
        self.assertEqual(courses, before)
        summary = academic_summary(courses)
        self.assertEqual(summary["points"], Decimal("13.25"))
        self.assertEqual(summary["units"], Decimal("5.25"))
        self.assertEqual((summary["graded"], summary["ungraded"]), (3, 1))
        self.assertEqual(len(summary["warnings"]), 2)

    def test_four_point_summary_breakdown_prediction_and_planners_agree(self):
        courses = [record("A", "A", Decimal("2.5")), record("B", "B", 1),
                   record("F", "F", 1), record("N", None, 2)]
        before = deepcopy(courses)
        summary = academic_summary(courses, policy=FOUR)
        detail = course_breakdown(courses, policy=FOUR)
        self.assertEqual((summary["points"], summary["units"]), (Decimal(13), Decimal("4.5")))
        self.assertEqual(summary["gpa"], detail["gpa"])
        self.assertEqual(detail["semesters"][0]["courses"][0]["grade_points"], Decimal(4))
        prediction = predicted_summary(courses, {code: "A" for code in ("A", "B", "F", "N")}, policy=FOUR)
        self.assertEqual(prediction["gpa"], 4)
        plan = target_plan(courses, 4, 2, policy=FOUR)
        self.assertEqual(plan["status"], "impossible")
        projection = projected_cgpa(courses, 4, 2, policy=FOUR)
        with localcontext() as context:
            context.prec = 50
            self.assertEqual(projection["projected"], Decimal(21) / Decimal("6.5"))
        self.assertEqual(courses, before)

    def test_grade_validation_and_target_limits_follow_selected_scale(self):
        self.assertEqual(checked_grade(" b ", policy=FOUR), "B")
        self.assertIsNone(checked_grade("", policy=FOUR))
        for grade in ("E", "Z", 0):
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                checked_grade(grade, policy=FOUR)
        self.assertEqual(checked_target("4.0000", policy=FOUR), 4)
        for target in ("4.0001", -1, True, "3.00001"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                checked_target(target, policy=FOUR)
        self.assertEqual(checked_target(5), 5)
        with self.assertRaises(ValueError):
            predicted_summary([record("X", None)], {"X": "E"}, policy=FOUR)

    def test_ungraded_f_duplicate_and_semester_order_remain_unchanged(self):
        courses = [record("N", None, 3, "Second"), record("N", "A"),
                   record("F", "F", 2, "First"), record("E", "E")]
        result = academic_summary(courses, policy=FOUR)
        self.assertEqual([s["semester"] for s in result["semesters"]], ["Second", "First"])
        self.assertEqual((result["gpa"], result["units"], result["ungraded"]), (0, 2, 1))
        self.assertEqual(len(result["warnings"]), 2)

    def test_target_plan_uses_selected_policy_for_current_quality_points(self):
        courses = [record("A", "A", 2), record("B", "B", 1),
                   record("F", "F", 1), record("N", None, 5)]
        before = deepcopy(courses)
        plan = target_plan(courses, 3, 4, policy=FOUR)
        # Four-point current quality points = 2*4 + 1*3 + 1*0 = 11.
        # Required = (3*8 - 11)/4 = 3.25; using legacy points yields 2.5.
        self.assertEqual(plan["current"]["points"], Decimal(11))
        self.assertEqual(plan["current"]["units"], Decimal(4))
        self.assertEqual(plan["total"], Decimal(8))
        self.assertEqual(plan["required"], Decimal("3.25"))
        self.assertEqual(plan["status"], "achievable")
        self.assertEqual(courses, before)

    def test_target_plan_rejects_target_above_selected_maximum(self):
        courses = [record("A", "A", 1)]
        with self.assertRaises(ValueError):
            target_plan(courses, "4.5", 3, policy=FOUR)
        # The same target remains valid under the explicit legacy default.
        self.assertEqual(target_plan(courses, "4.5", 3)["status"], "achievable")

    def test_projection_rejects_expected_average_above_selected_maximum(self):
        courses = [record("A", "A", 1)]
        with self.assertRaises(ValueError):
            projected_cgpa(courses, "4.5", 3, policy=FOUR)
        self.assertEqual(projected_cgpa(courses, "4.5", 3)["projected"], Decimal("4.625"))

    def test_legacy_invalid_grade_message_is_preserved(self):
        for value in ("Z", 0, None):
            for kwargs in ({}, {"policy": LEGACY_POLICY}):
                with self.subTest(value=value, kwargs=kwargs):
                    with self.assertRaises(ValueError) as caught:
                        checked_grade(value, allow_ungraded=False, **kwargs)
                    self.assertEqual(str(caught.exception), "Grades must be letters A to F.")

    def test_empty_and_target_status_boundaries(self):
        self.assertIsNone(academic_summary([], policy=FOUR)["gpa"])
        self.assertEqual(target_plan([], 4, 3, policy=FOUR)["status"], "achievable")
        self.assertEqual(target_plan([], 0, 3, policy=FOUR)["status"], "guaranteed")
        # 4.5 is impossible on this scale but achievable under the old hard-coded 5.
        boundary = target_plan([record("FAIL", "F", 1)], 4, 8, policy=FOUR)
        self.assertEqual(boundary["required"], Decimal("4.5"))
        self.assertEqual(boundary["status"], "impossible")
        self.assertEqual(projected_cgpa([], 4, 3, policy=FOUR)["projected"], 4)


class PolicyMutationTests(unittest.TestCase):
    def test_policy_regressions_are_detected_in_isolated_source_copies(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "academic_logic.py").read_text()
        mutations = {
            "ignore_selected_grade_points":
                ("policy.grade_points[grade]", "LEGACY_POLICY.grade_points[grade]"),
            "hardcoded_planner_maximum": ("required > policy.maximum", "required > 5"),
            "drop_prediction_policy":
                ("academic_summary(hypothetical, policy=policy)", "academic_summary(hypothetical)"),
        }
        # These single-call mutations reproduce reviewer P9, P11, P12 and L3.
        current_prefix = ("target = checked_target(target, policy=policy)\n"
                          "    remaining = checked_credits(remaining)\n"
                          "    current = academic_summary(courses")
        mutations.update({
            "target_current_uses_legacy_policy":
                (current_prefix + ", policy=policy)", current_prefix + ")"),
            "target_validation_uses_legacy_policy":
                ("target = checked_target(target, policy=policy)", "target = checked_target(target)"),
            "projection_validation_uses_legacy_policy":
                ("expected = checked_target(expected, policy=policy)", "expected = checked_target(expected)"),
            "legacy_grade_error_changed":
                ('"Grades must be letters A to F."', '"Grades must be A-F."'),
        })
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "grading_policy.py").write_text((root / "grading_policy.py").read_text())
            (target / "test_grading_policy.py").write_text(Path(__file__).read_text())
            # Only calculation tests run in children, so mutation checks cannot recurse.
            command = [sys.executable, "-B", "-m", "unittest", "test_grading_policy.PolicyCalculationTests"]
            (target / "academic_logic.py").write_text(source)
            control = subprocess.run(command, cwd=target, capture_output=True, text=True, timeout=30)
            self.assertEqual(control.returncode, 0, control.stderr)
            for name, (before, after) in mutations.items():
                with self.subTest(mutation=name):
                    self.assertIn(before, source)  # a no-op mutation cannot count as detected
                    (target / "academic_logic.py").write_text(source.replace(before, after))
                    # Avoid stale timestamp-based bytecode when replacing equal-sized files.
                    result = subprocess.run(command, cwd=target,
                                            capture_output=True, text=True, timeout=30,
                                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("FAIL:", result.stderr)
                    self.assertNotIn("ERROR:", result.stderr)
