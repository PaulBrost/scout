from django.urls import path
from . import views

urlpatterns = [
    path('', views.builder_view, name='builder'),
    path('api/chat/', views.api_chat, name='builder_chat'),
    path('api/save/', views.api_save, name='builder_save'),
    path('api/delete/', views.api_delete, name='builder_delete'),
]
