import time
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from web_tests.base import WebsiteCase


class Cost(WebsiteCase):
    def count(self, fn):
        with CaptureQueriesContext(connections['runtime']) as r, CaptureQueriesContext(connections['auth']) as a, CaptureQueriesContext(connections['default']) as d:
            t = time.perf_counter(); resp = fn(); ms = (time.perf_counter() - t) * 1000
        return resp.status_code, len(r), len(a), len(d), round(ms)

    def test_cost(self):
        self.seed()
        print('\nPROBE C01 anon GET login (status, runtime q, auth q, migrator q, ms):', self.count(lambda: Client().get(reverse('accounts:login'))))
        for name in ('dashboard', 'course-list', 'overview', 'predictor', 'planner'):
            print(f'PROBE C02 {name}:', self.count(lambda: self.client_a.get(reverse('student_web:' + name))))
        big = Client(REMOTE_ADDR='10.7.7.7').post(reverse('accounts:login'), {'username': 'a', 'password': 'b', 'pad': 'x' * 70000})
        many = Client(REMOTE_ADDR='10.7.7.8').post(reverse('accounts:login'), {f'f{i}': '1' for i in range(700)})
        print('PROBE C03 70KB body / 700 fields:', big.status_code, many.status_code)
