from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='users'),
    path('new/', views.user_new, name='user_new'),
    path('<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('create/', views.user_create, name='user_create'),
    path('<int:user_id>/update/', views.user_update, name='user_update'),
    path('<int:user_id>/delete/', views.user_delete, name='user_delete'),
]
