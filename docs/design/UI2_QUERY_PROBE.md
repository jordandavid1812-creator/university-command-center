# UI2 baseline-versus-new query observation

Companion to [UI2 implementation evidence](UI2_IMPLEMENTATION.md). Observation only, synthetic fixtures and the existing PostgreSQL restricted-role runner. No application code or query implementation is changed.

The exact baseline commit must be present locally: `ed8890982d99b7be5262d997e2e76266a4b65b0c`. The observation replaces only dashboard.html with the baseline through a test-only locmem loader, warms existing role checks and compares whole-request query counts on three aliases. It prints counts only, never SQL, HMAC values, credentials or student records.

Save the following as ignored `work/ui2_query_observation.py` in the UI2 checkout, use the existing private PostgreSQL security-test environment, and run:

```sh
PYTHONPATH="$PWD/work" PGTESTDATABASE=test_ui2_query_observation python server/manage.py test ui2_query_observation --settings=config.settings.web_test -v 1
```

PGTESTDATABASE must be disposable and distinct from the scratch database, following the existing auth/web test instructions. Never use actual student data.

```python
"""Independent local old/new template query observation. Synthetic rows only."""
from copy import deepcopy
from contextlib import ExitStack
import json,subprocess
from django.conf import settings
from django.db import connections
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from auth_tests.base import AuthenticationCase

BASE='ed8890982d99b7be5262d997e2e76266a4b65b0c'

class QueryObservation(AuthenticationCase):
    def test_baseline_and_ui2_read_counts_match(self):
        old=subprocess.check_output(['git','show',BASE+':server/student_web/templates/student_web/dashboard.html'],text=True)
        config=deepcopy(settings.TEMPLATES)
        config[0]['APP_DIRS']=False
        config[0]['OPTIONS']['loaders']=[('django.template.loaders.locmem.Loader',{'student_web/dashboard.html':old}),'django.template.loaders.app_directories.Loader']
        self.login()
        for state in ('empty','populated'):
            if state=='populated':self.seed()
            self.client_a.get('/')  # Warm role-boundary checks before comparison.
            def measure():
                with ExitStack() as stack:
                    queries={n:stack.enter_context(CaptureQueriesContext(connections[n])) for n in ('default','runtime','auth')}
                    response=self.client_a.get('/')
                self.assertEqual(response.status_code,200)
                return {n:len(q) for n,q in queries.items()}
            with override_settings(TEMPLATES=config):before=measure()
            after=measure()
            self.assertEqual(before,after)
            print('UI2_QUERY_EVIDENCE='+json.dumps(dict(state=state,baseline=before,ui2=after),sort_keys=True))
```

Observed PostgreSQL 17.11 result: one method passed. Both empty and populated requests were **auth=20, runtime=20, default/migrator=0 before and after**. [Captured JSON](evidence/ui2/query-counts.json). This does not establish production latency or a performance SLA. Ongoing CI additionally enforces zero reads when rendering loaded context and preserves the historical request query-budget/no-N+1 checks.
