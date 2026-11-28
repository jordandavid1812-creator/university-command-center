import uuid
from django.conf import settings
from django.urls import reverse

DISPLAY_COOKIE = 'ucc_display'
DISPLAY_CHOICES = ('system', 'light', 'dark')
# Essential-cookie notice (owner's choice): '1' once the student presses OK. Nothing else is stored.
COOKIE_NOTICE_COOKIE = 'ucc_cookie_ok'


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
        # (route, label, group). A group caption is shown above the first link of each group.
        for name, label, group in (
            ('dashboard', 'Dashboard', ''),
            ('course-list', 'Courses', 'Records'), ('semester-list', 'Semesters', 'Records'),
            ('assignment-list', 'Assignments', 'Records'),
            ('timetable', 'Timetable', 'Planning'), ('study-plans', 'Study planner', 'Planning'),
            ('material-list', 'Study materials', 'Planning'),
            ('overview', 'GPA & CGPA', 'Results'), ('predictor', 'GPA Predictor', 'Results'),
            ('planner', 'Target CGPA Planner', 'Results'),
            ('settings', 'Account settings', 'Account'),
        ):
            url = reverse('student_web:' + name)
            active = request.path == url if name == 'dashboard' else request.path.startswith(url)
            # AI requests and results belong to Study materials.
            if name == 'material-list' and request.path.startswith(ai_prefixes()):
                active = True
            starts_group = bool(group) and (not items or items[-1]['group'] != group)
            items.append({'url': url, 'label': label, 'active': active, 'group': group,
                          'starts_group': starts_group})
    # The phone's bottom tab bar: four of the same links, with the same "current page" rule.
    by_label = {item['label']: item for item in items}
    tabbar = [{**by_label[label], 'tab': tab, 'icon': icon} for label, tab, icon in (
        ('Dashboard', 'Home', 'home'), ('GPA & CGPA', 'Grades', 'grades'),
        ('Study materials', 'Study', 'study'), ('Study planner', 'Plan', 'plan')) if label in by_label]
    return {'website_enabled': enabled, 'workspace_authenticated': authenticated,
            'navigation': items, 'tabbar': tabbar,
            'page_section': next((item['label'] for item in items if item['active']), ''),
            'student_username': request.user.username if authenticated else '',
            'display_theme': display_theme(request),
            'cookie_notice': (enabled and getattr(settings, 'UCC_COOKIE_NOTICE', False) is True
                              and request.COOKIES.get(COOKIE_NOTICE_COOKIE) != '1')}
