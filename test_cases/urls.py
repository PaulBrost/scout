from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='test_cases'),
    path('api/save/', views.api_save, name='test_cases_save'),
    path('api/dry-run/', views.api_dry_run, name='test_cases_dry_run'),
    path('api/associate/', views.api_associate, name='test_cases_associate'),
    path('api/list/', views.api_list, name='api_test_cases_list'),
]
