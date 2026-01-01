# core/models.py
import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from PIL import Image

# AUTH user reference (string in settings)
User = settings.AUTH_USER_MODEL


# ------------------------------
# Image optimization helper
# ------------------------------
def optimize_image_file(uploaded_file, max_width=1200, quality=75, convert_to_webp=True):
    """
    Accepts an UploadedFile or a file-like object.
    Returns a ContentFile containing an optimized image (WebP by default).
    """
    try:
        img = Image.open(uploaded_file)
    except Exception:
        return None

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    width, height = img.size
    if max_width and width > max_width:
        ratio = max_width / float(width)
        new_height = int(height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    buffer = BytesIO()
    if convert_to_webp:
        out_format = "WEBP"
        ext = ".webp"
        save_kwargs = {"quality": quality, "method": 6}
    else:
        out_format = img.format or "JPEG"
        ext = os.path.splitext(getattr(uploaded_file, "name", "image"))[1] or ".jpg"
        save_kwargs = {"quality": quality}

    img.save(buffer, format=out_format, **save_kwargs)
    buffer.seek(0)

    original_name = getattr(uploaded_file, "name", "image")
    base, _ = os.path.splitext(original_name)
    new_name = f"{base}{ext}"

    return ContentFile(buffer.read(), name=new_name)


# =========================
# USER (custom)
# =========================
class User(AbstractUser):
    ROLE_CHOICES = (
        ("landlord", "Landlord"),
        ("renter", "Renter"),
    )

    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="renter")
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        # Optimize avatar on upload (smaller max_width)
        try:
            if self.avatar and getattr(self.avatar, "name", None) and not str(self.avatar.name).lower().endswith(".webp"):
                optimized = optimize_image_file(self.avatar, max_width=600, quality=70)
                if optimized:
                    self.avatar = optimized
        except Exception:
            pass
        super().save(*args, **kwargs)


# =========================
# LOCATION MODELS
# =========================
class Region(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class District(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=140)

    class Meta:
        unique_together = ("region", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.region.name})"


# =========================
# FACILITIES (AMENITIES)
# =========================
class Facility(models.Model):
    key = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


DEFAULT_FACILITIES = [
    ("wifi", "Wi-Fi"),
    ("internet", "Internet"),
    ("tv", "TV"),
    ("kitchen", "Kitchen"),
    ("washing_machine", "Washing Machine"),
    ("free_parking", "Free Parking"),
    ("paid_parking", "Paid Parking"),
    ("air_conditioning", "Air Conditioning"),
    ("dedicated_workspace", "Dedicated Workspace"),
    ("workspace", "Workspace"),
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
    PROPERTY_TYPES = (
        ("land", "Land"),
        ("house", "House"),
        ("apartment", "Apartment"),
        ("room", "Room"),
        ("office", "Office"),
    )

    LISTING_TYPES = (("sale", "For Sale"), ("rent", "For Rent"))

    landlord = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="properties")
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name="properties")

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=300, blank=True)

    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, default="house")
    category = models.CharField(max_length=10, choices=LISTING_TYPES, default="rent", help_text="Defines whether property is for SALE or RENT")

    price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    land_size_sqm = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    bedrooms = models.PositiveIntegerField(null=True, blank=True)
    bathrooms = models.PositiveIntegerField(null=True, blank=True)

    featured = models.BooleanField(default=False, help_text="Highlight/featured property")
    is_available = models.BooleanField(default=True)

    facilities = models.ManyToManyField(Facility, blank=True, related_name="properties", help_text="Select facilities/amenities for this property")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        category_label = self.get_category_display() if hasattr(self, "get_category_display") else self.category
        return f"{self.title} ({category_label})"

    def clean(self):
        if self.category == "sale":
            self.monthly_rent = None
        if self.category == "rent":
            self.price = None

        if self.property_type == "land":
            self.category = "sale"
            self.monthly_rent = None
            self.bedrooms = None
            self.bathrooms = None

        if self.property_type == "office":
            self.bedrooms = None
            if self.bathrooms == "":
                self.bathrooms = None


# =========================
# PROPERTY IMAGES
# =========================
class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="properties/%Y/%m/%d/")
    thumbnail = models.ImageField(upload_to="properties/thumbnails/%Y/%m/%d/", null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"Image for {self.property.title}"

    def _is_new_file(self):
        try:
            name = getattr(self.image, "name", "") or ""
            if name.lower().endswith(".webp"):
                return False
            if self.pk:
                existing = PropertyImage.objects.filter(pk=self.pk).first()
                if existing:
                    existing_name = getattr(existing.image, "name", "") or ""
                    if existing_name == name:
                        return False
            return True
        except Exception:
            return False

    def save(self, *args, **kwargs):
        try:
            if self.image and self._is_new_file():
                optimized = optimize_image_file(self.image, max_width=1200, quality=75, convert_to_webp=True)
                if optimized:
                    # set optimized main image
                    self.image = optimized

                    # create thumbnail from the optimized file
                    try:
                        thumb_file = optimize_image_file(self.image, max_width=400, quality=65, convert_to_webp=True)
                        if thumb_file:
                            self.thumbnail = thumb_file
                    except Exception:
                        pass
        except Exception:
            pass
        super().save(*args, **kwargs)


# =========================
# APPLICATIONS
# =========================
class Application(models.Model):
    STATUS_CHOICES = (("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected"))

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="applications")
    renter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.property.title} - {self.status}"


# =========================
# MESSAGES
# =========================
class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_messages")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


# =========================
# BANNERS
# =========================
class Banner(models.Model):
    title = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to="banner/")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Banner {self.id}"

    def save(self, *args, **kwargs):
        try:
            name = getattr(self.image, "name", "") or ""
            if self.image and not name.lower().endswith(".webp"):
                optimized = optimize_image_file(self.image, max_width=1400, quality=75, convert_to_webp=True)
                if optimized:
                    self.image = optimized
        except Exception:
            pass
        super().save(*args, **kwargs)


# =========================
# OTP / Password Reset
# =========================
class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)

    def __str__(self):
        return f"{self.user} - {self.code}"


# =========================
# NOTIFICATIONS
# =========================
class Notification(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class UserNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "notification")
