from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/trend/', views.api_trend, name='api_trend'),
    path('api/ai-flags/', views.api_ai_flags, name='api_ai_flags'),
]
