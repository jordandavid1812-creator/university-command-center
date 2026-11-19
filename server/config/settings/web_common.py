from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

DATABASE_FILE_LIMIT = 10 * 1024 * 1024  # academics.models.MAX_MATERIAL_BYTES
FORM_FIELDS_ALLOWANCE = 65536  # title, course, CSRF token and multipart boundaries


def set_upload_cap(namespace, limit):
    """The largest study file this deployment accepts, and the request size that allows it.
    Never above the database limit, which stays 10 MiB so stored files are untouched."""
    if type(limit) is not int or not 1 <= limit <= DATABASE_FILE_LIMIT:
        raise ImproperlyConfigured('UCC_MAX_UPLOAD_BYTES must be between 1 byte and 10 MiB.')
    namespace['UCC_MAX_UPLOAD_BYTES'] = limit
    namespace['FILE_UPLOAD_MAX_MEMORY_SIZE'] = limit + FORM_FIELDS_ALLOWANCE


def configure(namespace):
    namespace['STUDENT_WEBSITE_ENABLED'] = True
    namespace['ROOT_URLCONF'] = 'config.web_urls'
    namespace['INSTALLED_APPS'] = namespace['INSTALLED_APPS'] + [
        'django.contrib.staticfiles', 'django.contrib.messages', 'student_web']
    namespace['MIDDLEWARE'] = namespace['MIDDLEWARE'] + ['django.contrib.messages.middleware.MessageMiddleware']
    namespace['TEMPLATES'][0]['OPTIONS']['context_processors'] += [
        'django.contrib.messages.context_processors.messages', 'student_web.context.navigation']
    namespace['STATIC_URL'] = '/static/'
    namespace['STATIC_ROOT'] = Path(__file__).resolve().parents[3] / 'work' / 'static'
    namespace['MESSAGE_STORAGE'] = 'django.contrib.messages.storage.cookie.CookieStorage'
    namespace['TIME_ZONE'] = 'Africa/Lagos'
    namespace['DATA_UPLOAD_MAX_MEMORY_SIZE'] = 65536
    namespace['DATA_UPLOAD_MAX_NUMBER_FIELDS'] = 600
    # Study uploads: 10 MiB file plus 64 KiB for other fields. Keep in memory only;
    # never spill to a temporary file on disk. Keep in step with upload_validation.py.
    # Deployments with a smaller request limit (Vercel) lower it with set_upload_cap.
    set_upload_cap(namespace, DATABASE_FILE_LIMIT)
    namespace['FILE_UPLOAD_HANDLERS'] = ['django.core.files.uploadhandler.MemoryFileUploadHandler']
    namespace['CSRF_FAILURE_VIEW'] = 'student_web.views.csrf_failure'
    namespace['UCC_LOCAL_STATIC'] = False
