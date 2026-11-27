from django.core.management import call_command
from django.test.runner import DiscoverRunner


class SecurityTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        result = super().setup_databases(**kwargs)
        call_command("configure_runtime", verbosity=0)
        return result
