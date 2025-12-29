# core/management/commands/seed_facilities.py
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Facility

FACILITIES = [
    ("wifi", "Wi-Fi"),
    ("tv", "TV"),
    ("kitchen", "Kitchen"),
    ("washing_machine", "Washing Machine"),
    ("free_parking", "Free Parking"),
    ("paid_parking", "Paid Parking"),
    ("air_conditioning", "Air Conditioning"),
    ("dedicated_workspace", "Dedicated Workspace"),
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
]


class Command(BaseCommand):
    help = "Seed default Facility objects (safe to run multiple times)."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        for key, name in FACILITIES:
            obj, created = Facility.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'}: {key} -> {name}"))
        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created_count}, Updated: {updated_count}"))
