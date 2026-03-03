from django.urls import path
from . import views

urlpatterns = [
    path('ai/', views.ai_settings, name='admin_ai'),
    path('ai/prompt/', views.update_prompt, name='admin_update_prompt'),
    path('ai/tools/<str:tool_id>/toggle/', views.toggle_tool, name='admin_toggle_tool'),
    path('ai/settings/', views.update_settings, name='admin_update_settings'),
    path('ai/text-analysis/', views.update_text_analysis, name='admin_update_text_analysis'),
    path('ai/vision-analysis/', views.update_vision_analysis, name='admin_update_vision_analysis'),
]
