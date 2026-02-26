from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core.views import (
    dashboard_view, custom_logout_view, data_upload_view, mutual_funds_view,
    pms_aif_view, upload_portal_login_view, upload_portal_view, delete_file_view,
)
from core.views_root import root_redirect, website_view, about_us_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', custom_logout_view, name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', root_redirect, name='root-redirect'),
    path('website/', website_view, name='website'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('mutual-funds/', mutual_funds_view, name='mutual_funds'),
    path('pms-aif/', pms_aif_view, name='pms_aif'),
    path('about-us/', about_us_view, name='about_us'),
    path('api/data-upload/', data_upload_view, name='data_upload'),
    # Upload Portal (prerana-only)
    path('upload-portal/login/', upload_portal_login_view, name='upload_portal_login'),
    path('upload-portal/', upload_portal_view, name='upload_portal'),
    path('api/delete-file/', delete_file_view, name='delete_file'),
]
