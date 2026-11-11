from copy import deepcopy
from .security_test import *  # noqa: F403
from .auth_common import configure
configure(globals())
DATABASES["auth"]["TEST"] = {"MIRROR": "default"}
STUDENT_DB_ALIAS = "runtime"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AUTH_LINK_ORIGIN = "http://testserver"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
TEST_RUNNER = "auth_tests.runner.AuthenticationTestRunner"
