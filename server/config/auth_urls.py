from django.urls import include, path
from accounts import views

account_patterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('verify/request/', views.email_request, {'purpose': 'verify'}, name='resend'),
    path('verify/<uuid:selector>/<str:secret>/', views.verify, name='verify'),
    path('reset/', views.email_request, {'purpose': 'reset'}, name='reset'),
    path('reset/<uuid:selector>/<str:secret>/', views.reset_confirm, name='reset-confirm'),
    path('password/change/', views.password_change, name='password-change'),
    path('academic/', views.academic, name='academic'),
    path('academic/courses/<uuid:identifier>/', views.course, name='course'),
    path('academic/assignments/<uuid:identifier>/delete/', views.delete_assignment, name='delete-assignment'),
]
urlpatterns = [path('accounts/', include((account_patterns, 'accounts')))]
