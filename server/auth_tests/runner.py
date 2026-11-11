from django.core.management import call_command
from security_tests.runner import SecurityTestRunner


class AuthenticationTestRunner(SecurityTestRunner):
    def setup_databases(self, **kwargs):
        result = super().setup_databases(**kwargs)
        call_command('configure_auth_role', verbosity=0)
        return result
