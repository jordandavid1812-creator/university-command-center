"""Called by explicit web/test profiles; never adds migration credentials."""
from copy import deepcopy
from pathlib import Path


def configure(namespace):
    from accounts.log_privacy import configure as configure_privacy
    configure_privacy(namespace)
    from accounts.failure_response import validate_retry_after
    namespace["UCC_FAILURE_RETRY_AFTER"] = validate_retry_after(namespace.get("UCC_FAILURE_RETRY_AFTER", 5))
    required = namespace["required"]
    namespace["INSTALLED_APPS"] = namespace["INSTALLED_APPS"] + ["django.contrib.sessions"]
    namespace["DATABASES"]["auth"] = deepcopy(namespace["DATABASES"]["default"])
    namespace["DATABASES"]["auth"].update(USER=required("UCC_AUTH_ROLE"), PASSWORD=required("UCC_AUTH_PASSWORD"))
    namespace["DATABASE_ROUTERS"] = ["accounts.routing.AuthenticationRouter"]
    namespace["ROOT_URLCONF"] = "config.auth_urls"
    namespace["MIDDLEWARE"] = [
        "django.middleware.security.SecurityMiddleware",
        "accounts.middleware.ContentSecurityPolicyMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "accounts.middleware.DatabaseRoleBoundaryMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "accounts.middleware.AuthFailureMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
    namespace["TEMPLATES"] = [{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [Path(__file__).resolve().parents[2] / "accounts" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request", "django.template.context_processors.csrf",
            "django.contrib.auth.context_processors.auth",
        ]},
    }]
    namespace["AUTH_PASSWORD_VALIDATORS"] = deepcopy(namespace["AUTH_PASSWORD_VALIDATORS"])
    for validator in namespace["AUTH_PASSWORD_VALIDATORS"]:
        if validator["NAME"].endswith("MinimumLengthValidator"):
            # Owner's choice: 8 characters (12 felt too long for students). Common, all-number and
            # username-like passwords are still refused, and sign-in attempts are rate-limited.
            validator["OPTIONS"] = {"min_length": 8}
    namespace.update(
        AUTHENTICATION_BACKENDS=["accounts.backends.StudentBackend"],
        SESSION_ENGINE="django.contrib.sessions.backends.db",
        SESSION_COOKIE_AGE=1800, SESSION_EXPIRE_AT_BROWSER_CLOSE=True,
        SESSION_SAVE_EVERY_REQUEST=False, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True, CSRF_COOKIE_HTTPONLY=True, CSRF_COOKIE_SAMESITE="Lax",
        SECURE_REFERRER_POLICY="same-origin",
        LOGIN_URL="accounts:login", LOGIN_REDIRECT_URL="accounts:academic",
        LOGOUT_REDIRECT_URL="accounts:login", AUTHENTICATION_REQUIRED_FOR_CAPABILITIES=True,
        ALLOW_INTERNAL_TEST_PRINCIPALS=False,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@localhost", EMAIL_TIMEOUT=10,
        AUTH_LINK_ORIGIN="http://127.0.0.1:8000",
        AUTH_RATE_LIMITS={"login": (10, 900), "register": (5, 3600), "reset": (5, 3600),
                          "resend": (5, 3600), "verify": (20, 3600), "reset-confirm": (20, 3600),
                          "password-change": (5, 900), "verify-code": (20, 3600),
                          "delete-account": (5, 3600), "change-email": (5, 3600),
                          "change-email-code": (20, 3600)},
        # S0-01: forwarded headers are never trusted until a reviewed deployment
        # topology lists its proxy networks here. Keep empty in every profile.
        UCC_TRUSTED_PROXIES=(),
        # Launch step 3: invite-only sign-up. Off for the local website; web_production turns it
        # on and its system check (accounts.E106) refuses to start the public site without it.
        UCC_REQUIRE_INVITE=False,
        # Open sign-up with a 6-digit email code (accounts.signup_codes). Off locally, where the
        # original email link is used; the public profiles turn it on (check accounts.E106).
        UCC_SIGNUP_CODE=False,
    )
    # B1a only: application aliases; test/offline migrator defaults stay untouched.
    from accounts.dbsafety import apply_db_safety
    apply_db_safety(namespace)
