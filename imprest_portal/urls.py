"""
URL configuration for imprest_portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from utils.dashboard import DashboardView
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('users.urls') ),
    path('api/expense-items/', include('expenseitems.urls')),
    path('api/roles/', include('roles.urls')),
    path('api/stores/', include('stores.urls')),
    path('api/purchase-requests/', include('purchases.urls')),
    path('api/', include('reimbursements.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/dashboard/', DashboardView.as_view(), name='dashboard-view'),
    path('api/banks/', include('banks.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
