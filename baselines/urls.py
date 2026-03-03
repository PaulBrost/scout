from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='baselines'),
    path('api/approve/<uuid:baseline_id>/', views.api_approve, name='baseline_approve'),
    path('api/reject/<uuid:baseline_id>/', views.api_reject, name='baseline_reject'),
]
