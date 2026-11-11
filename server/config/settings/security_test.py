"""Migrator sets up tests; separate runtime login executes security checks."""
from copy import deepcopy
from .test import *  # noqa: F403

UCC_CONTEXT_SIGNING_KEY = required("UCC_CONTEXT_SIGNING_KEY")
STUDENT_DB_ALIAS = "runtime"
DATABASES["runtime"] = deepcopy(DATABASES["default"])
DATABASES["runtime"]["USER"] = required("UCC_RUNTIME_ROLE")
DATABASES["runtime"]["PASSWORD"] = required("UCC_RUNTIME_PASSWORD")
DATABASES["runtime"]["TEST"] = {"MIRROR": "default"}
TEST_RUNNER = "security_tests.runner.SecurityTestRunner"
