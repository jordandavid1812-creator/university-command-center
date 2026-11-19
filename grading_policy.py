"""Immutable letter-grade rules for pure calculations, not verified university policies.

A policy covers one calculation only. Applicability, publication, numeric scores,
repeats and mixed-policy transcripts require later, separately reviewed work.
"""
from dataclasses import dataclass
from decimal import Decimal
import re
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GradingPolicy:
    """A named revision with exact nonnegative grade points and an explicit ceiling.

    Input rules are copied into a read-only mapping. This prevents a caller changing
    the meaning of a calculation by mutating the dictionary used to construct it.
    Only built-in integers and finite Decimals are accepted; no float rounding.
    Identifiers are local references, not evidence of institutional verification.
    """

    identifier: str
    revision: str
    grade_points: Mapping[str, Decimal]
    maximum: Decimal

    def __post_init__(self):
        for value in (self.identifier, self.revision):
            if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
                raise ValueError("Policy identifiers must be bounded ASCII references.")
        maximum = self._points(self.maximum)
        if not 0 < maximum <= 100:
            raise ValueError("Policy maximum must be greater than zero and at most 100.")
        if not isinstance(self.grade_points, Mapping) or not 1 <= len(self.grade_points) <= 26:
            raise ValueError("Supply between one and 26 letter-grade rules.")
        copied = {}
        for grade, points in self.grade_points.items():
            if type(grade) is not str or not re.fullmatch(r"[A-Z]", grade):
                raise ValueError("Grade labels must be single uppercase ASCII letters.")
            points = self._points(points)
            if not 0 <= points <= maximum:
                raise ValueError("Grade points must be within the policy scale.")
            copied[grade] = points
        if max(copied.values()) != maximum or min(copied.values()) != 0:
            raise ValueError("Rules must include both zero and the policy maximum.")
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "grade_points", MappingProxyType(copied))

    @staticmethod
    def _points(value):
        if type(value) not in (int, Decimal):
            raise ValueError("Grade points must be exact integers or Decimals.")
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number > 100:
            raise ValueError("Grade points must be finite and between zero and 100.")
        # Avoid context-dependent quantization, including very large exponents.
        digits = number.as_tuple().digits
        exponent = number.as_tuple().exponent
        while digits and digits[-1] == 0:
            digits = digits[:-1]
            exponent += 1
        if number != 0 and exponent < -4:
            raise ValueError("Grade points support at most four decimal places.")
        return number


LEGACY_POLICY = GradingPolicy(
    "ucc-legacy-five-point", "1",
    {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}, 5,
)

# The usual 4-point scale (launch: each student chooses 4- or 5-point in Settings). There is no E.
FOUR_POINT_POLICY = GradingPolicy(
    "ucc-four-point", "1",
    {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}, 4,
)

# The website's choice per student; "five" (the legacy scale) is the default.
SCALES = {"five": LEGACY_POLICY, "four": FOUR_POINT_POLICY}


def checked_policy(policy):
    """Reject missing/unknown policy objects rather than falling back silently."""
    if type(policy) is not GradingPolicy:
        raise ValueError("An explicit GradingPolicy is required.")
    return policy
