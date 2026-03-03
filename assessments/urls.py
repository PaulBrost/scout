from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='assessments'),
    path('<int:numeric_id>/', views.detail, name='assessment_detail'),
    path('api/list/', views.api_list, name='api_assessments_list'),
    path('api/delete-item/', views.api_delete_item, name='api_delete_item'),
    path('api/update-assessment/', views.api_update_assessment, name='api_update_assessment'),
    path('api/delete-assessment/', views.api_delete_assessment, name='api_delete_assessment'),
    path('api/delete-assessments/', views.api_delete_assessments_bulk, name='api_delete_assessments_bulk'),
    path('api/create-script/', views.api_create_script, name='api_create_script'),
]
