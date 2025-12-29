# rental_project/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import profile_me
from core.views import (
    PropertyViewSet,
    ApplicationViewSet,
    MessageViewSet,
    RegisterView,
    auth_me,
    RegionListView,
    DistrictListView,
    CustomTokenObtainPairView,
    BannerListView,
    FacilityListView,
    ChangePasswordView,
    DeleteAccountView,
    ForgotPasswordView,
    VerifyOTPView,
    ResetPasswordView,

    # 🔔 NOTIFICATIONS (FROM CORE)
    NotificationListAPIView,
    mark_notification_read,
    mark_all_notifications_read,
)

# --------------------
# DRF Routers
# --------------------
router = DefaultRouter()
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'messages', MessageViewSet, basename='message')

# --------------------
# URL Patterns
# --------------------
urlpatterns = [
    path('admin/', admin.site.urls),

    # API routers
    path('api/', include(router.urls)),

    # Locations
    path('api/regions/', RegionListView.as_view(), name='regions-list'),
    path('api/districts/', DistrictListView.as_view(), name='districts-list'),

    # Facilities
    path('api/facilities/', FacilityListView.as_view(), name='facilities-list'),

    # Banners
    path('api/banners/', BannerListView.as_view(), name='banner-list'),

    # Profile
    path('api/profile/me/', profile_me, name='profile-me'),

    # Auth
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/me/', auth_me, name='auth-me'),

    # Password
    path('api/auth/password/change/', ChangePasswordView.as_view(), name='password_change'),
    path('api/auth/delete-account/', DeleteAccountView.as_view(), name='delete-account'),

    # Forgot password (OTP)
    path('api/auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('api/auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('api/auth/reset-password/', ResetPasswordView.as_view(), name='reset-password'),

    # 🔔 NOTIFICATIONS (CORE)
    path('api/notifications/', NotificationListAPIView.as_view(), name='notifications-list'),
    path('api/notifications/<int:pk>/mark-read/', mark_notification_read, name='notification-mark-read'),
    path('api/notifications/mark-all-read/', mark_all_notifications_read, name='notifications-mark-all-read'),

    # DRF browsable auth (dev)
    path('api-auth/', include('rest_framework.urls')),
]

# --------------------
# Media
# --------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
