from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='users'),
    path('new/', views.user_new, name='user_new'),
    path('stop-impersonate/', views.user_stop_impersonate, name='user_stop_impersonate'),
    path('<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('create/', views.user_create, name='user_create'),
    path('<int:user_id>/update/', views.user_update, name='user_update'),
    path('<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('<int:user_id>/impersonate/', views.user_impersonate, name='user_impersonate'),
]
