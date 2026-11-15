from django.urls import path
from . import views

app_name = 'student_web'
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('semesters/', views.semester_list, name='semester-list'),
    path('courses/', views.course_list, name='course-list'),
    path('assignments/', views.assignment_list, name='assignment-list'),
    path('performance/', views.overview, name='overview'),
    path('predictor/', views.predictor, name='predictor'),
    path('planner/', views.planner, name='planner'),
    path('settings/', views.settings, name='settings'),
    path('settings/display/', views.display_preference, name='display-preference'),
    path('settings/profile/', views.profile_edit, name='profile-edit'),
    path('settings/export/', views.data_export, name='data-export'),
    path('materials/new/', views.material_upload, name='material-upload'),
    path('materials/', views.material_list, name='material-list'),
    path('materials/<uuid:identifier>/delete/', views.delete, {'kind': 'material'}, name='material-delete'),
    path('materials/<uuid:identifier>/download/', views.material_download, name='material-download'),
]
for kind, plural in (('semester', 'semesters'), ('course', 'courses'), ('assignment', 'assignments')):
    urlpatterns += [
        path(f'{plural}/new/', views.edit, {'kind': kind}, name=kind + '-create'),
        path(f'{plural}/<uuid:identifier>/edit/', views.edit, {'kind': kind}, name=kind + '-edit'),
        path(f'{plural}/<uuid:identifier>/delete/', views.delete, {'kind': kind}, name=kind + '-delete'),
    ]
urlpatterns += [path('assignments/<uuid:identifier>/status/', views.assignment_status, name='assignment-status')]
