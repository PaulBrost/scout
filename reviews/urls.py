from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='reviews'),
    path('action/', views.review_action, name='review_action'),
    path('api/list/', views.api_list, name='api_reviews_list'),
    path('suppressions/', views.suppressions, name='review_suppressions'),
    path('suppressions/<uuid:suppression_id>/delete/', views.delete_suppression, name='delete_suppression'),
]
