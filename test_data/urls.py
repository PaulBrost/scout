from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='test_data'),
    path('new/', views.detail, name='test_data_new'),
    path('<uuid:dataset_id>/', views.detail, name='test_data_detail'),
    path('api/save/', views.api_save, name='test_data_save'),
    path('api/save/<uuid:dataset_id>/', views.api_save, name='test_data_update'),
    path('api/delete/<uuid:dataset_id>/', views.api_delete, name='test_data_delete'),
]
