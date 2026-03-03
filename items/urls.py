from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='items'),
    path('<int:numeric_id>/', views.detail, name='item_detail'),
    path('api/list/', views.api_list, name='api_items_list'),
]
