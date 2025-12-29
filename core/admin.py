# core/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import (
    User,
    Region,
    District,
    Property,
    PropertyImage,
    Application,
    Message,
    Banner,
    Facility,
)

User = get_user_model()


# =========================
# USER ADMIN
# =========================
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'role', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'phone')
    list_filter = ('role', 'is_staff', 'is_active')
    ordering = ('-date_joined',)


# =========================
# BANNER ADMIN
# =========================
@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title',)
    ordering = ('-created_at',)


# =========================
# LOCATION ADMIN
# =========================
@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'region')
    list_filter = ('region',)
    search_fields = ('name',)


# =========================
# FACILITY ADMIN
# =========================
@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ('id', 'key', 'name')
    search_fields = ('key', 'name')
    ordering = ('name',)


# =========================
# PROPERTY IMAGE INLINE
# =========================
class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1
    fields = ('image',)
    show_change_link = True


# =========================
# PROPERTY ADMIN
# =========================
@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'property_type',
        'category',
        'landlord',
        'region',
        'district',
        'price',
        'monthly_rent',
        'is_available',
        'created_at',
    )

    list_filter = (
        'property_type',
        'category',
        'is_available',
        'region',
        'district',
    )

    search_fields = (
        'title',
        'address',
        'landlord__username',
        'landlord__email',
    )

    readonly_fields = ('created_at',)
    filter_horizontal = ('facilities',)  # ✅ THIS ENABLES FACILITY SELECTION UI
    inlines = [PropertyImageInline]

    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'description', 'address')
        }),
        ('Location', {
            'fields': ('region', 'district', 'lat', 'lng')
        }),
        ('Property Details', {
            'fields': (
                'property_type',
                'category',
                'bedrooms',
                'bathrooms',
                'land_size_sqm',
            )
        }),
        ('Pricing', {
            'fields': ('price', 'monthly_rent')
        }),
        ('Facilities', {
            'fields': ('facilities',)
        }),
        ('Status', {
            'fields': ('is_available', 'created_at')
        }),
    )


# =========================
# APPLICATION ADMIN
# =========================
@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('id', 'property', 'renter', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = (
        'property__title',
        'renter__username',
        'renter__email',
    )


# =========================
# MESSAGE ADMIN
# =========================
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'receiver', 'created_at')
    search_fields = (
        'sender__username',
        'receiver__username',
    )
    list_filter = ('created_at',)


# core/admin.py
from django.contrib import admin
from .models import Notification, UserNotification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'message')


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification', 'read', 'read_at')
    list_filter = ('read',)
