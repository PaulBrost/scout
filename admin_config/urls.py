from django.urls import path
from . import views

urlpatterns = [
    path('ai/', views.ai_settings, name='admin_ai'),
    path('ai/prompt/', views.update_prompt, name='admin_update_prompt'),
    path('ai/tools/<str:tool_id>/toggle/', views.toggle_tool, name='admin_toggle_tool'),
    path('ai/settings/', views.update_settings, name='admin_update_settings'),
    path('ai/text-analysis/', views.update_text_analysis, name='admin_update_text_analysis'),
    path('ai/vision-analysis/', views.update_vision_analysis, name='admin_update_vision_analysis'),
    path('ai/test-provider/', views.test_provider, name='admin_test_provider'),
    path('ai/feature-provider/', views.save_feature_provider, name='admin_save_feature_provider'),
    path('general/', views.general_settings, name='admin_general'),
    path('general/update/', views.update_general_settings, name='admin_update_general'),
    path('archives/', views.test_archives, name='admin_archives'),
    path('archives/restore/', views.restore_archive, name='admin_restore_archive'),
    path('archives/delete/', views.delete_archive, name='admin_delete_archive'),
    path('archives/cleanup/', views.run_cleanup, name='admin_run_cleanup'),
]
