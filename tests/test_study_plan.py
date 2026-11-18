"""Study planner arithmetic: topics shared out evenly before the exam, revision days kept free."""
import unittest
from datetime import date, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from student_web.study_plan import review_dates, spread, study_days, topic_lines  # noqa: E402

TODAY = date(2026, 11, 18)


class StudyPlanTests(unittest.TestCase):
    def test_even_spread_keeps_the_last_day_for_revision(self):
        exam = TODAY + timedelta(days=6)  # study days: 18th to 22nd, revision 23rd, exam 24th
        self.assertEqual(study_days(TODAY, exam, 1), [TODAY + timedelta(days=n) for n in range(5)])
        dates = spread(10, TODAY, exam, 1)
        self.assertEqual([dates.count(TODAY + timedelta(days=n)) for n in range(5)], [2, 2, 2, 2, 2])
        self.assertEqual(dates, sorted(dates))  # topic order is kept
        self.assertEqual(review_dates(TODAY, exam, 1), [TODAY + timedelta(days=5)])

    def test_fewer_topics_than_days_and_uneven_counts(self):
        exam = TODAY + timedelta(days=11)  # 10 study days, 1 revision day
        self.assertEqual(spread(3, TODAY, exam, 1), [TODAY, TODAY + timedelta(days=3), TODAY + timedelta(days=6)])
        counts = [spread(7, TODAY, TODAY + timedelta(days=4), 0).count(TODAY + timedelta(days=n)) for n in range(4)]
        self.assertEqual(sum(counts), 7)
        self.assertLessEqual(max(counts) - min(counts), 1)

    def test_exam_too_close_for_revision_days_uses_every_day(self):
        tomorrow = TODAY + timedelta(days=1)
        self.assertEqual(spread(4, TODAY, tomorrow, 3), [TODAY] * 4)
        self.assertEqual(review_dates(TODAY, tomorrow, 3), [])
        self.assertEqual(study_days(TODAY, TODAY + timedelta(days=3), 3), [TODAY, TODAY + timedelta(days=1),
                                                                          TODAY + timedelta(days=2)])

    def test_exam_today_or_past_is_refused(self):
        for exam in (TODAY, TODAY - timedelta(days=1)):
            with self.subTest(exam=exam), self.assertRaises(ValueError):
                spread(1, TODAY, exam, 0)
        self.assertEqual(spread(0, TODAY, TODAY + timedelta(days=2), 1), [])

    def test_topic_lines(self):
        self.assertEqual(topic_lines("  OSI   model \n\n TCP\r\nTCP \n"), ['OSI model', 'TCP', 'TCP'])


if __name__ == '__main__':
    unittest.main()
