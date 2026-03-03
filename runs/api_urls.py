from django.urls import path
from . import views

urlpatterns = [
    path('runs/latest/', views.api_latest, name='api_latest'),
    path('runs/list/', views.api_list, name='api_runs_list'),
]
