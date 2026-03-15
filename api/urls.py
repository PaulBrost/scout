from django.urls import path
from . import views

urlpatterns = [
    # Health (no auth)
    path('health/', views.health, name='api_v1_health'),

    # Scripts
    path('scripts/', views.scripts, name='api_v1_scripts'),
    path('scripts/<int:script_id>/', views.script_detail, name='api_v1_script_detail'),
    path('scripts/<int:script_id>/run/', views.script_run, name='api_v1_script_run'),

    # Suites
    path('suites/', views.suites, name='api_v1_suites'),
    path('suites/<uuid:suite_id>/', views.suite_detail_view, name='api_v1_suite_detail'),
    path('suites/<uuid:suite_id>/run/', views.suite_run_view, name='api_v1_suite_run'),

    # Runs
    path('runs/', views.runs, name='api_v1_runs'),
    path('runs/<uuid:run_id>/', views.run_detail, name='api_v1_run_detail'),
    path('runs/<uuid:run_id>/status/', views.run_status, name='api_v1_run_status'),
]
