# core/serializers.py
import json
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import update_last_login

from rest_framework import serializers
from .models import Notification, UserNotification
from rest_framework import serializers
from django.contrib.auth import password_validation
from django.utils.translation import gettext_lazy as _
from .models import (
    Banner, Region, District, Property, PropertyImage,
    Application, Message, Facility
)

User = get_user_model()


# ---------------- User ----------------
class UserSerializer(serializers.ModelSerializer):
    # allow frontend 'name' to map to first_name
    name = serializers.CharField(source='first_name', required=False, allow_blank=True)
    # Allow file upload and normal representation for avatar
    avatar = serializers.ImageField(required=False, allow_null=True, use_url=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'name', 'first_name', 'last_name',
            'email', 'phone', 'bio', 'avatar', 'role', 'date_joined'
        ]
        read_only_fields = ['id', 'username', 'role', 'date_joined']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request', None)
        avatar_val = rep.get('avatar', None)
        if avatar_val and request and isinstance(avatar_val, str):
            if not avatar_val.startswith('http://') and not avatar_val.startswith('https://'):
                try:
                    rep['avatar'] = request.build_absolute_uri(avatar_val)
                except Exception:
                    rep['avatar'] = avatar_val
        return rep


# ---------------- Register ----------------
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'role', 'phone']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            role=validated_data.get('role', 'renter'),
            phone=validated_data.get('phone', '')
        )
        return user


# ---------------- Region / District ----------------
class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name']


class DistrictSerializer(serializers.ModelSerializer):
    region = RegionSerializer(read_only=True)

    class Meta:
        model = District
        fields = ['id', 'name', 'region']


# ---------------- PropertyImage ----------------
class PropertyImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = PropertyImage
        fields = ['id', 'image', 'uploaded_at']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request', None)
        img = rep.get('image')
        if img and request and isinstance(img, str):
            if not img.startswith('http://') and not img.startswith('https://'):
                try:
                    rep['image'] = request.build_absolute_uri(img)
                except Exception:
                    rep['image'] = img
        return rep


# ---------------- Facility ----------------
class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ["id", "key", "name"]


# ---------------- Banner ----------------
class BannerSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = ['id', 'title', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            try:
                return request.build_absolute_uri(obj.image.url)
            except Exception:
                return obj.image.url
        return None


# ---------------- Property ----------------
class PropertySerializer(serializers.ModelSerializer):
    landlord = UserSerializer(read_only=True)
    images = PropertyImageSerializer(many=True, read_only=True)
    region = RegionSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)

    # facilities read + write
    facilities = FacilitySerializer(many=True, read_only=True)

    # Accept "facility_ids": [1,2] in JSON body (mapped to 'facilities' internally)
    facility_ids = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(), many=True, write_only=True, required=False, source='facilities'
    )

    # write-only FK fields for incoming ids
    region_id = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(), write_only=True, source='region', required=False, allow_null=True
    )
    district_id = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.all(), write_only=True, source='district', required=False, allow_null=True
    )

    class Meta:
        model = Property
        fields = [
            'id', 'landlord', 'title', 'description', 'address', 'lat', 'lng',
            'property_type', 'category', 'price', 'monthly_rent', 'land_size_sqm',
            'bedrooms', 'bathrooms', 'region', 'district', 'region_id', 'district_id',
            'is_available', 'images', 'created_at', 'featured',
            'facilities', 'facility_ids',
        ]
        read_only_fields = ['id', 'landlord', 'images', 'created_at', 'facilities']

    def _parse_facilities_input(self, raw):
        """
        Accepts raw input from initial_data (string JSON, comma-separated, or list).
        Returns a list/queryset of Facility instances (can be empty list).
        Supports numeric ids, string keys (facility.key) or names.
        """
        if raw is None:
            return []

        # if the frontend sent a JSON string, try to parse
        if isinstance(raw, str):
            raw_str = raw.strip()
            # handle comma-separated like "wifi,gym"
            if raw_str.startswith('[') or raw_str.startswith('{'):
                try:
                    parsed = json.loads(raw_str)
                except Exception:
                    parsed = raw_str
            elif ',' in raw_str:
                parsed = [s.strip() for s in raw_str.split(',') if s.strip()]
            else:
                # single token e.g. "wifi" or "1"
                parsed = [raw_str]
        else:
            parsed = raw

        if parsed is None:
            return []

        # normalize to list
        if not isinstance(parsed, (list, tuple)):
            parsed = [parsed]

        # separate numeric ids and potential keys/names
        ids = []
        keys = []
        names = []
        for item in parsed:
            if item is None:
                continue
            if isinstance(item, (int,)):
                ids.append(int(item))
                continue
            s = str(item).strip()
            if s == '':
                continue
            # numeric-looking strings
            if s.isdigit():
                ids.append(int(s))
                continue
            # otherwise treat as key/name
            keys.append(s)

        found = []
        if ids:
            qs = Facility.objects.filter(id__in=ids)
            found.extend(list(qs))
        if keys:
            # first try key field (exact)
            qs_key = Facility.objects.filter(key__in=keys)
            found_keys = {str(f.key) for f in qs_key}
            found.extend(list(qs_key))
            # try keys not matched -> try name case-insensitive
            remaining = [k for k in keys if k not in found_keys]
            if remaining:
                qs_name = Facility.objects.filter(name__iexact__in=remaining)
                # NOTE: name__iexact__in is not supported directly in all Django versions; instead iterate
                # fall back to manual lookup:
                extra = []
                for r in remaining:
                    try:
                        f = Facility.objects.filter(name__iexact=r).first()
                        if f:
                            extra.append(f)
                    except Exception:
                        pass
                found.extend(extra)
        # dedupe by id
        unique = []
        seen = set()
        for f in found:
            if f and f.id not in seen:
                seen.add(f.id)
                unique.append(f)
        return unique

    def _get_incoming_facilities(self):
        """
        Return list of Facility instances based on validated_data or raw initial_data.
        This normalizes several formats so frontend can send:
         - facility_ids: [1,2]
         - facilities: "[1,2]"  (JSON string)
         - facilities: "wifi,gym" (comma-separated keys)
         - facilities: ["wifi","gym"] (list of keys)
        """
        # If DRF already validated and provided 'facilities' in validated_data (from facility_ids field), use it.
        # Note: When PrimaryKeyRelatedField with source='facilities' is used, validated_data will contain 'facilities'.
        validated_facilities = None
        # validated_data is not directly available here; we'll rely on caller to pass the validated list if present.
        return None  # caller will handle: create/update will call validated_data.pop('facilities', None) first

    def validate(self, data):
        """
        Conditional validation based on property_type ('land') and listing category.
        Accepts partial updates too.
        """
        ptype = data.get('property_type', getattr(self.instance, 'property_type', None))
        category = data.get('category', getattr(self.instance, 'category', None))
        errors = {}

        ptype = (ptype and str(ptype).lower()) or None
        category = (category and str(category).lower()) or None

        if ptype == 'land':
            if (data.get('land_size_sqm') is None) and (getattr(self.instance, 'land_size_sqm', None) is None):
                errors['land_size_sqm'] = 'Land size (sqm) is required for land properties.'
            if (data.get('price') is None) and (getattr(self.instance, 'price', None) is None):
                errors['price'] = 'Price is required for land properties.'
        else:
            if category == 'sale':
                if (data.get('price') is None) and (getattr(self.instance, 'price', None) is None):
                    errors['price'] = 'Sale price is required for sale listings.'
            if category == 'rent':
                if (data.get('monthly_rent') is None) and (getattr(self.instance, 'monthly_rent', None) is None):
                    errors['monthly_rent'] = 'Monthly rent is required for rent listings.'

        if ptype == 'house':
            if (data.get('bedrooms') is None) and (getattr(self.instance, 'bedrooms', None) is None):
                errors['bedrooms'] = 'Number of bedrooms is recommended for houses.'

        if errors:
            raise serializers.ValidationError(errors)
        return data

    def _existing_image_filenames(self, instance):
        """
        Helper: returns set of existing image filenames for property instance.
        We use filename dedupe; adapt if you prefer hash-based dedupe.
        """
        names = set()
        if not instance:
            return names
        for img in instance.images.all():
            try:
                fname = getattr(img.image, 'name', '')
            except Exception:
                fname = ''
            if fname:
                names.add(fname.split('/')[-1])
        return names

    def create(self, validated_data):
        """
        Create property, attach facilities and multipart images (dedupe by filename).
        Landlord will be request.user if authenticated.
        """
        request = self.context.get('request', None)

        # Primary path: DRF will put facility instances in 'facilities' when facility_ids was present.
        facilities = validated_data.pop('facilities', None)

        # If none found in validated_data, try parsing raw incoming data (forms may send strings)
        if facilities is None and request is not None:
            raw = request.data.get('facility_ids') or request.data.get('facilities')
            if raw is not None:
                parsed = self._parse_facilities_input(raw)
                facilities = parsed

        # protect landlord from client-provided value
        validated_data.pop('landlord', None)

        user = getattr(request, 'user', None)
        landlord_to_use = None
        if user and getattr(user, 'is_authenticated', False):
            landlord_to_use = user

        if landlord_to_use:
            prop = Property.objects.create(landlord=landlord_to_use, **validated_data)
        else:
            prop = Property.objects.create(**validated_data)

        # attach facilities if any (list of model instances)
        if facilities is not None:
            try:
                prop.facilities.set(facilities)
            except Exception as e:
                print("[DEBUG] Failed to set facilities on create:", e, "incoming:", facilities)

        # handle images
        if request is not None:
            uploaded = request.FILES.getlist('images')
            existing_names = self._existing_image_filenames(prop)
            for f in uploaded:
                fname = getattr(f, 'name', '') or ''
                short = fname.split('/')[-1]
                if short in existing_names:
                    continue
                PropertyImage.objects.create(property=prop, image=f)
                existing_names.add(short)

        # debug log
        try:
            print("[DEBUG] Created Property id:", prop.id, "facilities after create:", list(prop.facilities.values_list("id", "key", "name")))
        except Exception:
            pass

        return prop

    def update(self, instance, validated_data):
        """
        Update fields, replace facilities if provided, append new images deduped by filename.
        """
        request = self.context.get('request', None)

        # Primary path: DRF validated 'facilities' when facility_ids present
        facilities = validated_data.pop('facilities', None)

        # If not present, try parsing raw incoming data (forms might send strings)
        if facilities is None and request is not None:
            # only update facilities if client provided something
            if 'facility_ids' in request.data or 'facilities' in request.data:
                raw = request.data.get('facility_ids') or request.data.get('facilities')
                facilities = self._parse_facilities_input(raw)

        validated_data.pop('landlord', None)  # do not allow landlord change

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if facilities is not None:
            try:
                instance.facilities.set(facilities)
            except Exception as e:
                print("[DEBUG] Failed to set facilities on update:", e, "incoming:", facilities)

        if request is not None:
            uploaded = request.FILES.getlist('images')
            existing_names = self._existing_image_filenames(instance)
            for f in uploaded:
                fname = getattr(f, 'name', '') or ''
                short = fname.split('/')[-1]
                if short in existing_names:
                    continue
                PropertyImage.objects.create(property=instance, image=f)
                existing_names.add(short)

        # debug
        try:
            print("[DEBUG] Updated Property id:", instance.id, "facilities after update:", list(instance.facilities.values_list("id", "key", "name")))
        except Exception:
            pass

        return instance


# ---------------- Application ----------------
class ApplicationSerializer(serializers.ModelSerializer):
    renter = UserSerializer(read_only=True)
    property = PropertySerializer(read_only=True)
    property_id = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(), write_only=True, source='property'
    )

    class Meta:
        model = Application
        fields = ['id', 'property', 'property_id', 'renter', 'message', 'status', 'created_at']
        read_only_fields = ['id', 'renter', 'created_at']

    def create(self, validated_data):
        validated_data['renter'] = self.context['request'].user
        return super().create(validated_data)


# ---------------- Message ----------------
class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    receiver_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), write_only=True, source='receiver'
    )

    class Meta:
        model = Message
        fields = ['id', 'sender', 'receiver', 'receiver_id', 'text', 'created_at']
        read_only_fields = ['id', 'sender', 'created_at']

    def create(self, validated_data):
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


# ---------------- Custom Token ----------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Allow login by username, email or phone. Returns tokens plus user info.
    """
    username_field = 'username'

    def validate(self, attrs):
        username_or_email_or_phone = attrs.get('username')
        password = attrs.get('password')

        user = None
        try:
            user = User.objects.get(username=username_or_email_or_phone)
        except User.DoesNotExist:
            try:
                user = User.objects.get(email=username_or_email_or_phone)
            except User.DoesNotExist:
                try:
                    user = User.objects.get(phone=username_or_email_or_phone)
                except User.DoesNotExist:
                    raise serializers.ValidationError('No active account found with the given credentials')

        if user and user.check_password(password):
            data = super().validate({'username': user.username, 'password': password})
            update_last_login(None, user)
            data.update({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': getattr(user, 'role', None),
                'phone': getattr(user, 'phone', None),
            })
            return data

        raise serializers.ValidationError('No active account found with the given credentials')



class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password1 = serializers.CharField(required=True)
    new_password2 = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Old password is incorrect."))
        return value

    def validate(self, data):
        if data['new_password1'] != data['new_password2']:
            raise serializers.ValidationError({"new_password2": _("The two new password fields didn't match.")})
        # Use Django's validators (length, common password, numeric, etc.)
        password_validation.validate_password(data['new_password1'], self.context['request'].user)
        return data





class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user
        password = attrs.get("password")

        if not password:
            raise serializers.ValidationError({
                "password": "Password is required to delete your account."
            })

        if not user.check_password(password):
            raise serializers.ValidationError({
                "password": "Incorrect password."
            })

        return attrs




class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField()




class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ('id','title','message','is_active','send_to_all','created_at','read')

    def get_read(self, obj):
        user = self.context.get('request').user
        if not user or user.is_anonymous:
            return False
        try:
            un = UserNotification.objects.get(user=user, notification=obj)
            return bool(un.read)
        except UserNotification.DoesNotExist:
            return False
