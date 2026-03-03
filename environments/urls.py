from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='environments'),
    path('new/', views.environment_new, name='environment_new'),
    path('<uuid:env_id>/edit/', views.environment_edit, name='environment_edit'),
    path('create/', views.environment_create, name='environment_create'),
    path('<uuid:env_id>/update/', views.environment_update, name='environment_update'),
    path('<uuid:env_id>/delete/', views.environment_delete, name='environment_delete'),
]
