import uuid
from django.conf import settings
from django.urls import reverse

DISPLAY_COOKIE = 'ucc_display'
DISPLAY_CHOICES = ('system', 'light', 'dark')


def display_theme(request):
    """This browser's display choice; anything unexpected falls back to System."""
    value = request.COOKIES.get(DISPLAY_COOKIE)
    return value if value in DISPLAY_CHOICES else 'system'


def ai_prefixes():
    """URL prefixes of the AI request and result pages, taken from the routes themselves."""
    sample = uuid.UUID(int=0)
    return tuple(reverse('student_web:' + name, args=[sample]).split(str(sample))[0]
                 for name in ('ai-request', 'ai-result'))


def navigation(request):
    enabled = getattr(settings, 'STUDENT_WEBSITE_ENABLED', False)
    authenticated = enabled and getattr(request, 'student_identity', None) is not None
    items = []
    if authenticated:
        for name, label in (
            ('dashboard', 'Dashboard'), ('course-list', 'Courses'), ('semester-list', 'Semesters'),
            ('assignment-list', 'Assignments'), ('timetable', 'Timetable'), ('study-plans', 'Study planner'),
            ('overview', 'GPA & CGPA'),
            ('predictor', 'GPA Predictor'),
            ('planner', 'Target CGPA Planner'), ('material-list', 'Study materials'),
            ('settings', 'Account settings'),
        ):
            url = reverse('student_web:' + name)
            active = request.path == url if name == 'dashboard' else request.path.startswith(url)
            # AI requests and results belong to Study materials.
            if name == 'material-list' and request.path.startswith(ai_prefixes()):
                active = True
            items.append({'url': url, 'label': label, 'active': active})
    return {'website_enabled': enabled, 'workspace_authenticated': authenticated,
            'navigation': items, 'student_username': request.user.username if authenticated else '',
            'display_theme': display_theme(request)}
