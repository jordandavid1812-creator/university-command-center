"""Opt-in local benchmark, excluded from ordinary test*.py discovery.

Use the disposable three-role PostgreSQL web_test profile only. The runner
creates/drops its database. Output contains aggregate measurements, not records.
Normal website tests do not run this timing experiment.
"""
import json
import statistics
import time
from datetime import date
from django.db import connections
from django.test.utils import CaptureQueriesContext
from academics.models import Assignment
from academics.ownership import database_alias, student_transaction
from academics.services import assignments, courses
from .base import WebsiteCase


class WebsiteBenchmark(WebsiteCase):
    def test_benchmark(self):
        self.seed()
        for index in range(60):
            course = courses.create(self.identity_a, semester_id=self.sem_a.pk,
                                    original_code=f'BENCH{index}', name=f'Synthetic course {index}',
                                    credit_units='3', actual_grade='A')
            assignments.create(self.identity_a, course_id=course.pk,
                               title=f'Synthetic task {index}', due_date=date(2026, 12, 1))
        output = {}
        for path in ('/', '/courses/', '/semesters/', '/assignments/?status=pending',
                     '/performance/', '/predictor/', '/planner/'):
            self.client_a.get(path)  # Warm the template/connection/role checks.
            samples, counts, sql_times = [], [], []
            for _ in range(7):
                with (CaptureQueriesContext(connections['runtime']) as runtime,
                      CaptureQueriesContext(connections['auth']) as auth,
                      CaptureQueriesContext(connections['default']) as migration):
                    start = time.perf_counter()
                    response = self.client_a.get(path)
                    samples.append((time.perf_counter() - start) * 1000)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(migration), 0)
                counts.append({'runtime': len(runtime), 'auth': len(auth), 'migration': len(migration)})
                sql_times.append(sum(float(q['time']) for q in list(runtime) + list(auth)) * 1000)
            output[path] = {
                'median_ms': round(statistics.median(samples), 2),
                'min_ms': round(min(samples), 2), 'max_ms': round(max(samples), 2),
                'sql_ms': round(statistics.median(sql_times), 2), 'queries': counts[0],
                'counts_stable': all(count == counts[0] for count in counts),
            }
        # Review the owner/date plan using the same signed runtime transaction.
        with student_transaction(self.identity_a):
            plan = json.loads(Assignment.objects.using(database_alias()).filter(
                owner_id=self.identity_a.student_id, completed=False).order_by('due_date', 'id')[:25]
                .explain(analyze=True, format='json'))[0]
            with connections[database_alias()].cursor() as cursor:
                cursor.execute("SELECT tablename, indexname FROM pg_catalog.pg_indexes "
                               "WHERE schemaname='public' AND tablename IN "
                               "('academics_semester','academics_course','academics_assignment') "
                               "ORDER BY tablename,indexname")
                indexes = cursor.fetchall()

        def nodes(node):
            children = [child for part in node.get('Plans', []) for child in nodes(part)]
            return [{'type': node['Node Type'], 'index': node.get('Index Name')}] + children

        output['plan_review'] = {'assignment_nodes': nodes(plan['Plan']),
                                 'execution_ms': plan['Execution Time'], 'existing_indexes': indexes}
        # Never print records, SQL parameters or credentials.
        print('WEBSITE_BENCHMARK=' + json.dumps(output, sort_keys=True))
