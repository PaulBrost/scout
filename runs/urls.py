from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='runs'),
    path('<uuid:run_id>/', views.detail, name='run_detail'),
    path('<uuid:run_id>/script/<uuid:script_id>/', views.script_detail, name='script_detail'),
]
