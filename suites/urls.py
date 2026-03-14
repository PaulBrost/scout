from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='suites'),
    path('new/', views.suite_new, name='suite_new'),
    path('<uuid:suite_id>/', views.suite_detail, name='suite_detail'),
    path('api/create/', views.suite_create, name='suite_create'),
    path('api/update/<uuid:suite_id>/', views.suite_update, name='suite_update'),
    path('api/delete/<uuid:suite_id>/', views.suite_delete, name='suite_delete'),
    path('<uuid:suite_id>/run/', views.suite_run, name='suite_run'),
    path('run-script/', views.run_script, name='run_script'),
    path('api/list/', views.api_list, name='api_suites_list'),
    path('api/scripts/', views.api_scripts_by_environment, name='api_scripts_by_environment'),
    path('api/assessments/', views.api_assessments_by_environment, name='api_assessments_by_environment'),
    path('api/items/', views.api_items_by_assessment, name='api_items_by_assessment'),
]
