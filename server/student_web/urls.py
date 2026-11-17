from django.urls import path
from . import ai_views, views

app_name = 'student_web'
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('semesters/', views.semester_list, name='semester-list'),
    path('courses/', views.course_list, name='course-list'),
    path('assignments/', views.assignment_list, name='assignment-list'),
    path('performance/', views.overview, name='overview'),
    path('predictor/', views.predictor, name='predictor'),
    path('planner/', views.planner, name='planner'),
    path('planner/projection/', views.planner_projection, name='planner-projection'),
    path('performance/print/', views.standing_print, name='standing-print'),
    path('settings/', views.settings, name='settings'),
    path('settings/display/', views.display_preference, name='display-preference'),
    path('settings/profile/', views.profile_edit, name='profile-edit'),
    path('settings/export/', views.data_export, name='data-export'),
    path('materials/new/', views.material_upload, name='material-upload'),
    path('materials/', views.material_list, name='material-list'),
    path('materials/<uuid:identifier>/delete/', views.delete, {'kind': 'material'}, name='material-delete'),
    path('materials/<uuid:identifier>/download/', views.material_download, name='material-download'),
    path('materials/<uuid:identifier>/tools/', ai_views.tools, name='ai-tools'),
    path('materials/<uuid:identifier>/tools/confirm/', ai_views.confirm, name='ai-confirm'),
    path('materials/<uuid:identifier>/tools/send/', ai_views.send, name='ai-send'),
    path('ai-requests/<uuid:identifier>/', ai_views.request_status, name='ai-request'),
    path('ai-results/<uuid:identifier>/', ai_views.result, name='ai-result'),
    path('ai-results/<uuid:identifier>/download/', ai_views.result_download, name='ai-result-download'),
    path('ai-results/<uuid:identifier>/delete/', ai_views.result_delete, name='ai-result-delete'),
]
for kind, plural in (('semester', 'semesters'), ('course', 'courses'), ('assignment', 'assignments')):
    urlpatterns += [
        path(f'{plural}/new/', views.edit, {'kind': kind}, name=kind + '-create'),
        path(f'{plural}/<uuid:identifier>/edit/', views.edit, {'kind': kind}, name=kind + '-edit'),
        path(f'{plural}/<uuid:identifier>/delete/', views.delete, {'kind': kind}, name=kind + '-delete'),
    ]
urlpatterns += [path('assignments/<uuid:identifier>/status/', views.assignment_status, name='assignment-status')]
