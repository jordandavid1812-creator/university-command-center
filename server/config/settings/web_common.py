from pathlib import Path


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
    namespace['CSRF_FAILURE_VIEW'] = 'student_web.views.csrf_failure'
    namespace['UCC_LOCAL_STATIC'] = False
