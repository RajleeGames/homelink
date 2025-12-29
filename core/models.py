# core/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# =========================
# USER
# =========================
class User(AbstractUser):
    ROLE_CHOICES = (
        ('landlord', 'Landlord'),
        ('renter', 'Renter'),
    )

    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='renter')
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.username


# =========================
# LOCATION MODELS
# =========================
class Region(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class District(models.Model):
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='districts'
    )
    name = models.CharField(max_length=140)

    class Meta:
        unique_together = ('region', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.region.name})"


# =========================
# FACILITIES (AMENITIES)
# =========================
class Facility(models.Model):
    """
    Reusable facility/amenity model. Properties can have many facilities.
    Use `key` for stable references (programmatic), `name` for display.
    """
    key = models.CharField(
        max_length=60,
        unique=True,
        help_text="Stable key (e.g. wifi, kitchen, paid_parking)"
    )
    name = models.CharField(max_length=120, help_text="Human friendly name (e.g. Wi-Fi, Kitchen)")
    description = models.TextField(blank=True, help_text="Optional description")
    icon = models.CharField(max_length=80, blank=True, help_text="Optional icon identifier for client UI")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# Recommended set of default facilities.
# These keys are chosen to match the frontend mapping (CreatePropertyScreen / PropertyDetailScreen).
DEFAULT_FACILITIES = [
    ("wifi", "Wi-Fi"),
    ("internet", "Internet"),                 # alternate/alias for wifi if used
    ("tv", "TV"),
    ("kitchen", "Kitchen"),
    ("washing_machine", "Washing Machine"),
    ("free_parking", "Free Parking"),
    ("paid_parking", "Paid Parking"),
    ("air_conditioning", "Air Conditioning"),
    ("dedicated_workspace", "Dedicated Workspace"),
    ("workspace", "Workspace"),               # alias used elsewhere
    ("pool", "Pool"),
    ("hot_tub", "Hot Tub"),
    ("fire_pit", "Fire Pit"),
    ("outdoor_dining", "Outdoor Dining"),
    ("beach_access", "Beach Access"),
    ("outdoor_shower", "Outdoor Shower"),
    ("smoking_area", "Smoking Area"),
    ("hot_water", "Hot Water"),
    ("pets_allowed", "Pets Allowed"),
    ("security", "Security"),
    ("gym", "Gym"),
    ("heating", "Heating"),
    ("parking", "Parking"),
    ("furnished", "Furnished"),
]


def create_default_facilities():
    """
    Convenience function to create the DEFAULT_FACILITIES.
    Call from Django shell after migrations:
      python manage.py shell
      from core.models import create_default_facilities
      create_default_facilities()
    """
    created = []
    for key, name in DEFAULT_FACILITIES:
        obj, did_create = Facility.objects.get_or_create(key=key, defaults={"name": name})
        if did_create:
            created.append(obj)
    return created


# =========================
# PROPERTY
# =========================
class Property(models.Model):

    # -------- TYPES --------
    PROPERTY_TYPES = (
        ('land', 'Land'),
        ('house', 'House'),
        ('apartment', 'Apartment'),
        ('room', 'Room'),
        ('office', 'Office'),
    )

    LISTING_TYPES = (
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
    )

    # -------- RELATIONS --------
    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='properties'
    )

    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='properties'
    )

    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='properties'
    )

    # -------- BASIC INFO --------
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=300, blank=True)

    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    # -------- PROPERTY LOGIC --------
    property_type = models.CharField(
        max_length=20,
        choices=PROPERTY_TYPES,
        default='house'
    )

    category = models.CharField(
        max_length=10,
        choices=LISTING_TYPES,
        default='rent',
        help_text='Defines whether property is for SALE or RENT'
    )

    # -------- PRICES --------
    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Sale price (used when category = sale)'
    )

    monthly_rent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Monthly rent (used when category = rent)'
    )

    # -------- LAND ONLY --------
    land_size_sqm = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    # -------- HOUSE / APARTMENT / ROOM only --------
    bedrooms = models.PositiveIntegerField(null=True, blank=True)
    bathrooms = models.PositiveIntegerField(null=True, blank=True)

    # -------- FEATURES --------
    featured = models.BooleanField(default=False, help_text="Highlight/featured property")
    is_available = models.BooleanField(default=True)

    # Facilities / amenities (Many-to-Many)
    facilities = models.ManyToManyField(
        Facility,
        blank=True,
        related_name='properties',
        help_text="Select facilities/amenities for this property"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        category_label = self.get_category_display() if hasattr(self, 'get_category_display') else self.category
        return f"{self.title} ({category_label})"

    # -------- SAFETY CLEANUP --------
    def clean(self):
        """
        Enforce correct price logic and type-specific rules.
        Note: ManyToMany (facilities) can't be modified here (not saved yet). Do only field-level adjustments.
        """
        # price vs monthly_rent logic
        if self.category == 'sale':
            self.monthly_rent = None

        if self.category == 'rent':
            self.price = None

        # enforce land-specific rules
        if self.property_type == 'land':
            # land listings are always for sale and don't have bedroom/bathroom/monthly rent
            self.category = 'sale'
            self.monthly_rent = None
            self.bedrooms = None
            self.bathrooms = None

        # office-specific: no bedrooms/bathrooms required (optional)
        if self.property_type == 'office':
            self.bedrooms = None
            # keep bathrooms optional; set to None if empty
            if self.bathrooms == '':
                self.bathrooms = None


# =========================
# PROPERTY IMAGES
# =========================
class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='properties/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"Image for {self.property.title}"


# =========================
# APPLICATIONS
# =========================
class Application(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    )

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='applications'
    )
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.property.title} - {self.status}"


# =========================
# MESSAGES
# =========================
class Message(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


# =========================
# BANNERS
# =========================
class Banner(models.Model):
    title = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='banner/')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title or f"Banner {self.id}"




class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)

    def __str__(self):
        return f"{self.user} - {self.code}"

# core/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Notification(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class UserNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'notification')
