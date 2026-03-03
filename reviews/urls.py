from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='reviews'),
    path('action/', views.review_action, name='review_action'),
    path('api/list/', views.api_list, name='api_reviews_list'),
]
