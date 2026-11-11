from datetime import date
from decimal import Decimal
from django.test import TransactionTestCase
from accounts.models import Student
from academics.ownership import identity_for_verified_student
from academics.services import semesters, courses, assignments


class StudentSecurityCase(TransactionTestCase):
    databases = {"default", "runtime"}

    def setUp(self):
        self.student_a = Student.objects.create_user("synthetic-a")
        self.student_b = Student.objects.create_user("synthetic-b")
        self.a = identity_for_verified_student(self.student_a)
        self.b = identity_for_verified_student(self.student_b)
        self.sem_a = semesters.create(self.a, label="A semester", display_order=0)
        self.sem_b = semesters.create(self.b, label="B semester", display_order=0)
        self.course_a = courses.create(self.a, semester_id=self.sem_a.pk, original_code="CSC101",
                                       name="Synthetic A", credit_units=Decimal("3"))
        self.course_b = courses.create(self.b, semester_id=self.sem_b.pk, original_code="CSC101",
                                       name="Synthetic B", credit_units=Decimal("3"), actual_grade="A")
        self.task_a = assignments.create(self.a, course_id=self.course_a.pk, title="A assignment",
                                          due_date=date(2026, 11, 11))
        self.task_b = assignments.create(self.b, course_id=self.course_b.pk, title="B assignment",
                                          due_date=date(2026, 11, 11))
