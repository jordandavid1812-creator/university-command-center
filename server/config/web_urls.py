from django.conf import settings
from django.urls import include, path, re_path
from django.contrib.staticfiles.views import serve

urlpatterns = [path('', include('student_web.urls')), path('', include('config.auth_urls'))]
if getattr(settings, 'UCC_LOCAL_STATIC', False):
    # Explicit local-only profile: bundled static files even while DEBUG stays off.
    urlpatterns += [re_path(r'^static/(?P<path>.*)$', serve, {'insecure': True})]
handler400 = 'student_web.views.bad_request'
handler403 = 'student_web.views.forbidden'
handler404 = 'student_web.views.not_found'
handler500 = 'student_web.views.server_error'
