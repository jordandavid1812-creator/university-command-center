"""Class-of-degree bands on the student profile: owner-only, and the database itself refuses
partial, out-of-range or out-of-order bands (the CHECK must not let NULL comparisons through)."""
from decimal import Decimal
from django.db import connections, DatabaseError, transaction
from academics.ownership import student_transaction
from academics.services import CLASS_BAND_FIELDS, InvalidRecord, profiles
from .base import StudentSecurityCase

GOOD = dict(zip(CLASS_BAND_FIELDS, map(Decimal, ("4.5", "3.5", "2.4", "1.5", "1.0"))))


class ClassBandSecurityTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def setUp(self):
        super().setUp()
        self.profile_a = profiles.create(self.a, display_name="Synthetic A")
        self.profile_b = profiles.create(self.b, display_name="Synthetic B", **GOOD)

    def refused_in_database(self, assignments):
        """Bypass the service and Django validation: the database CHECK alone must refuse."""
        columns = ", ".join(f"{name}=%s" for name in assignments)
        with student_transaction(self.a):
            with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
                self.sql(f"UPDATE academics_studentprofile SET {columns} WHERE id=%s",
                         [*assignments.values(), self.profile_a.pk])

    def test_runtime_role_may_save_and_clear_its_own_bands(self):
        with student_transaction(self.a):
            self.assertEqual(self.sql("UPDATE academics_studentprofile SET first_class_min=4.5, second_upper_min=3.5, "
                                      "second_lower_min=2.4, third_class_min=1.5, pass_min=1 WHERE id=%s",
                                      [self.profile_a.pk]), 1)
            self.assertEqual(self.sql("UPDATE academics_studentprofile SET first_class_min=NULL, second_upper_min=NULL, "
                                      "second_lower_min=NULL, third_class_min=NULL, pass_min=NULL WHERE id=%s",
                                      [self.profile_a.pk]), 1)
            # Another student's bands are invisible and unchangeable.
            self.assertEqual(self.sql("UPDATE academics_studentprofile SET pass_min=0.5 WHERE id=%s",
                                      [self.profile_b.pk]), 0)
        self.assertEqual(profiles.current(self.b).pass_min, Decimal("1.0000"))

    def test_database_refuses_partial_out_of_range_and_out_of_order_bands(self):
        self.refused_in_database({"first_class_min": Decimal("4.5")})  # one value alone (NULL comparison trap)
        self.refused_in_database({**GOOD, "pass_min": None})
        self.refused_in_database({**GOOD, "first_class_min": Decimal("5.5")})
        self.refused_in_database({**GOOD, "pass_min": Decimal("-0.1")})
        self.refused_in_database({**GOOD, "second_lower_min": Decimal("3.5")})  # equal to the class above
        self.refused_in_database({**GOOD, "third_class_min": Decimal("2.6")})  # above the class above

    def test_service_refuses_the_same_before_the_database(self):
        version = self.profile_a.record_version
        for bad in ({"first_class_min": Decimal("4.5")}, {**GOOD, "third_class_min": Decimal("2.6")}):
            with self.subTest(bad=bad), self.assertRaises(InvalidRecord):
                profiles.update(self.a, self.profile_a.pk, version=version, **bad)
        saved = profiles.update(self.a, self.profile_a.pk, version=version, **GOOD)
        self.assertEqual(saved.first_class_min, Decimal("4.5"))
