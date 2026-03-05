from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('login/', core_views.login_view, name='login'),
    path('logout/', core_views.logout_view, name='logout'),
    path('settings/', core_views.settings_view, name='settings'),
    path('', include('dashboard.urls')),
    path('runs/', include('runs.urls')),
    path('suites/', include('suites.urls')),
    path('items/', include('items.urls')),
    path('reviews/', include('reviews.urls')),
    path('assessments/', include('assessments.urls')),
    path('environments/', include('environments.urls')),
    path('test-cases/', include('test_cases.urls')),
    path('builder/', include('builder.urls')),
    path('baselines/', include('baselines.urls')),
    path('test-data/', include('test_data.urls')),
    path('admin-config/', include('admin_config.urls')),
    path('api/', include('runs.api_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
