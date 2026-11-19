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
    path('settings/delete-account/', views.account_delete, name='account-delete'),
    path('settings/change-email/', views.email_change, name='email-change'),
    path('settings/change-email/confirm/', views.email_change_confirm, name='email-change-confirm'),
    path('settings/display/', views.display_preference, name='display-preference'),
    path('settings/profile/', views.profile_edit, name='profile-edit'),
    path('settings/class-bands/', views.class_bands_edit, name='class-bands'),
    path('settings/class-bands/reset/', views.class_bands_reset, name='class-bands-reset'),
    path('settings/export/', views.data_export, name='data-export'),
    path('materials/new/', views.material_upload, name='material-upload'),
    path('materials/', views.material_list, name='material-list'),
    path('timetable/', views.timetable, name='timetable'),
    path('study-planner/', views.study_plans, name='study-plans'),
    path('study-planner/new/', views.study_plan_create, name='study-plan-create'),
    path('study-planner/<uuid:identifier>/', views.study_plan_detail, name='study-plan'),
    path('study-planner/<uuid:identifier>/replan/', views.study_plan_replan, name='study-plan-replan'),
    path('study-planner/<uuid:identifier>/topics/new/', views.study_topic_add, name='study-topic-add'),
    path('study-planner/<uuid:identifier>/delete/', views.delete, {'kind': 'plan'}, name='plan-delete'),
    path('study-topics/<uuid:identifier>/done/', views.study_topic_done, name='study-topic-done'),
    path('study-topics/<uuid:identifier>/delete/', views.study_topic_delete, name='study-topic-delete'),
    path('materials/search/', views.material_search, name='material-search'),
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
for kind, plural in (('semester', 'semesters'), ('course', 'courses'), ('assignment', 'assignments'), ('session', 'timetable')):
    urlpatterns += [
        path(f'{plural}/new/', views.edit, {'kind': kind}, name=kind + '-create'),
        path(f'{plural}/<uuid:identifier>/edit/', views.edit, {'kind': kind}, name=kind + '-edit'),
        path(f'{plural}/<uuid:identifier>/delete/', views.delete, {'kind': kind}, name=kind + '-delete'),
    ]
urlpatterns += [path('assignments/<uuid:identifier>/status/', views.assignment_status, name='assignment-status')]
