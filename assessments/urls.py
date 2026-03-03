from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='assessments'),
    path('<str:assessment_id>/', views.detail, name='assessment_detail'),
    path('api/list/', views.api_list, name='api_assessments_list'),
]
