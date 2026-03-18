from django.urls import path
from . import views

urlpatterns = [
    path('', views.feedback_form, name='feedback'),
    path('api/submit/', views.api_submit, name='feedback_submit'),
    # Admin views
    path('admin/', views.admin_list, name='feedback_admin'),
    path('admin/<uuid:feedback_id>/', views.admin_detail, name='feedback_admin_detail'),
    path('admin/delete/', views.admin_delete, name='feedback_admin_delete'),
]
