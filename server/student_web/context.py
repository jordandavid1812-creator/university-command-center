from django.conf import settings
from django.urls import reverse

DISPLAY_COOKIE = 'ucc_display'
DISPLAY_CHOICES = ('system', 'light', 'dark')


def display_theme(request):
    """This browser's display choice; anything unexpected falls back to System."""
    value = request.COOKIES.get(DISPLAY_COOKIE)
    return value if value in DISPLAY_CHOICES else 'system'


def navigation(request):
    enabled = getattr(settings, 'STUDENT_WEBSITE_ENABLED', False)
    authenticated = enabled and getattr(request, 'student_identity', None) is not None
    items = []
    if authenticated:
        for name, label, mark in (
            ('dashboard', 'Dashboard', '01'), ('course-list', 'Courses', '02'),
            ('semester-list', 'Semesters', '03'), ('assignment-list', 'Assignments', '04'),
            ('overview', 'GPA & CGPA', '05'), ('predictor', 'GPA Predictor', '06'),
            ('planner', 'Target CGPA Planner', '07'), ('material-list', 'Study materials', '08'),
            ('settings', 'Account settings', '09'),
        ):
            url = reverse('student_web:' + name)
            active = request.path == url if name == 'dashboard' else request.path.startswith(url)
            # AI requests and results belong to Study materials.
            if name == 'material-list' and request.path.startswith(('/ai-requests/', '/ai-results/')):
                active = True
            items.append({'url': url, 'label': label, 'mark': mark, 'active': active})
    return {'website_enabled': enabled, 'workspace_authenticated': authenticated,
            'navigation': items, 'student_username': request.user.username if authenticated else '',
            'display_theme': display_theme(request)}
