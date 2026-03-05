from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='items'),
    path('<int:numeric_id>/', views.detail, name='item_detail'),
    path('api/list/', views.api_list, name='api_items_list'),
    path('api/update-item/', views.api_update_item, name='api_update_item'),
    path('api/delete-item/', views.api_delete_item, name='api_delete_item_single'),
    path('api/delete-items/', views.api_delete_items_bulk, name='api_delete_items_bulk'),
    path('api/set-baseline/', views.api_set_baseline, name='api_set_baseline'),
    path('api/create-script/', views.api_create_script, name='api_create_item_script'),
]
