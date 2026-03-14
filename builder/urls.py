from django.urls import path
from . import views

urlpatterns = [
    path('', views.builder_view, name='builder'),
    path('api/chat/', views.api_chat, name='builder_chat'),
    path('api/chat-history/', views.api_chat_history, name='builder_chat_history'),
    path('api/save/', views.api_save, name='builder_save'),
    path('api/delete/', views.api_delete, name='builder_delete'),
    path('api/link-conversation/', views.api_link_conversation, name='builder_link_conversation'),
    path('api/update-summary/', views.api_update_summary, name='builder_update_summary'),
    path('api/clear-chat/', views.api_clear_chat, name='builder_clear_chat'),
    path('api/duplicate/', views.api_duplicate, name='builder_duplicate'),
    path('api/generate-baseline/', views.api_generate_baseline, name='builder_generate_baseline'),
    path('api/delete-baseline/', views.api_delete_baseline, name='builder_delete_baseline'),
    path('api/clear-baselines/', views.api_clear_baselines, name='builder_clear_baselines'),
]
