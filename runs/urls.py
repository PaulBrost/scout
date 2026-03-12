from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='runs'),
    path('<uuid:run_id>/', views.detail, name='run_detail'),
    path('<uuid:run_id>/status/', views.api_run_status, name='api_run_status'),
    path('<uuid:run_id>/script/<uuid:script_id>/', views.script_detail, name='script_detail'),
    path('<uuid:run_id>/screenshots/', views.api_run_screenshots, name='api_run_screenshots'),
    path('<uuid:run_id>/analyze/', views.api_run_analyze, name='api_run_analyze'),
    path('<uuid:run_id>/analyses/', views.api_run_analyses, name='api_run_analyses'),
    path('<uuid:run_id>/delete/', views.api_delete_run, name='api_delete_run'),
    path('api/delete-runs/', views.api_delete_runs_bulk, name='api_delete_runs_bulk'),
    path('screenshot/<uuid:screenshot_id>/flag/', views.api_flag_screenshot, name='api_flag_screenshot'),
    path('screenshot/img/<path:file_path>', views.serve_screenshot, name='serve_screenshot'),
]
