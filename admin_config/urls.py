from django.urls import path
from . import views

urlpatterns = [
    path('ai/', views.ai_settings, name='admin_ai'),
    path('ai/prompt/', views.update_prompt, name='admin_update_prompt'),
    path('ai/tools/<str:tool_id>/toggle/', views.toggle_tool, name='admin_toggle_tool'),
    path('ai/settings/', views.update_settings, name='admin_update_settings'),
    path('ai/text-analysis/', views.update_text_analysis, name='admin_update_text_analysis'),
    path('ai/vision-analysis/', views.update_vision_analysis, name='admin_update_vision_analysis'),
    path('ai/feature-provider/', views.save_feature_provider, name='admin_save_feature_provider'),
    # AI Provider CRUD
    path('ai/providers/', views.list_providers, name='admin_list_providers'),
    path('ai/providers/<uuid:provider_id>/', views.get_provider, name='admin_get_provider'),
    path('ai/providers/save/', views.save_provider, name='admin_save_provider'),
    path('ai/providers/delete/', views.delete_provider, name='admin_delete_provider'),
    path('ai/providers/test/', views.test_provider_connection, name='admin_test_provider_connection'),
    # General settings
    path('general/', views.general_settings, name='admin_general'),
    path('general/update/', views.update_general_settings, name='admin_update_general'),
    path('archives/', views.test_archives, name='admin_archives'),
    path('archives/restore/', views.restore_archive, name='admin_restore_archive'),
    path('archives/delete/', views.delete_archive, name='admin_delete_archive'),
    path('archives/cleanup/', views.run_cleanup, name='admin_run_cleanup'),
    # API client management
    path('api/', views.api_clients, name='admin_api_clients'),
    path('api/create/', views.api_client_create, name='admin_api_client_create'),
    path('api/<uuid:client_id>/edit/', views.api_client_edit, name='admin_api_client_edit'),
    path('api/<uuid:client_id>/update/', views.api_client_update, name='admin_api_client_update'),
    path('api/<uuid:client_id>/regenerate/', views.api_client_regenerate, name='admin_api_client_regenerate'),
    path('api/<uuid:client_id>/delete/', views.api_client_delete, name='admin_api_client_delete'),
]
