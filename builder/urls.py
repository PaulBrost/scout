from django.urls import path
from . import views

urlpatterns = [
    path('', views.builder_view, name='builder'),
    path('api/chat/', views.api_chat, name='builder_chat'),
    path('api/save/', views.api_save, name='builder_save'),
    path('api/record/start/', views.api_record_start, name='builder_record_start'),
    path('api/record/status/', views.api_record_status, name='builder_record_status'),
    path('api/record/stop/', views.api_record_stop, name='builder_record_stop'),
]
