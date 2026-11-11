from django.conf import settings
from django.urls import reverse


def navigation(request):
    enabled = getattr(settings, 'STUDENT_WEBSITE_ENABLED', False)
    authenticated = enabled and getattr(request, 'student_identity', None) is not None
    items = []
    if authenticated:
        for name, label, mark in (
            ('dashboard', 'Dashboard', '01'), ('course-list', 'Courses', '02'),
            ('semester-list', 'Semesters', '03'), ('assignment-list', 'Assignments', '04'),
            ('overview', 'GPA & CGPA', '05'), ('predictor', 'GPA Predictor', '06'),
            ('planner', 'Target CGPA Planner', '07'), ('settings', 'Account settings', '08'),
        ):
            url = reverse('student_web:' + name)
            items.append({'url': url, 'label': label, 'mark': mark,
                          'active': request.path == url if name == 'dashboard' else request.path.startswith(url)})
    return {'website_enabled': enabled, 'workspace_authenticated': authenticated,
            'navigation': items, 'student_username': request.user.username if authenticated else ''}
