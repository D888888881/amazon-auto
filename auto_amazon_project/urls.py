"""
URL configuration for auto_amazon_project project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from auto_amazon import views as amazon_views

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='index', permanent=False)),
    path('login/', amazon_views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', amazon_views.register, name='register'),
    path('amazon/', include('auto_amazon.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
