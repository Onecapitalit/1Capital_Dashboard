"""
URL configuration for SalesDashboard project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from core.views import dashboard_view
from core.views_root import root_redirect

# Note: We are no longer importing user_login/user_logout here because we are using
# Django's built-in auth views, included via 'django.contrib.auth.urls'.

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', root_redirect, name='root-redirect'),
    path('dashboard/', dashboard_view, name='dashboard'),
]