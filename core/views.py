# core/views.py
from rest_framework import viewsets, permissions, generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import models
from rest_framework.generics import ListAPIView
from .models import Banner
from .serializers import BannerSerializer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Facility
from .serializers import FacilitySerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import ChangePasswordSerializer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
import random
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import PasswordResetOTP
from .serializers import (
    ForgotPasswordSerializer,
    VerifyOTPSerializer,
    ResetPasswordSerializer
)



from .models import (
    Region, District,
    Property, PropertyImage,
    Application, Message
)
from .serializers import (
    RegionSerializer, DistrictSerializer,
    PropertySerializer, ApplicationSerializer, MessageSerializer,
    RegisterSerializer, UserSerializer,
    CustomTokenObtainPairSerializer
)

User = get_user_model()


# ================= Register View =================
class RegisterView(generics.CreateAPIView):
    """
    Register new user.
    """
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data.get('username')
        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


# ================= Region / District List Views =================
class RegionListView(generics.ListAPIView):
    queryset = Region.objects.all().order_by('name')
    serializer_class = RegionSerializer
    permission_classes = [permissions.AllowAny]


class DistrictListView(generics.ListAPIView):
    serializer_class = DistrictSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = District.objects.select_related('region').all().order_by('name')
        region_id = self.request.query_params.get('region', None)
        if region_id:
            qs = qs.filter(region_id=region_id)
        return qs


# ================= Property ViewSet =================
class PropertyViewSet(viewsets.ModelViewSet):
    """
    Handles create (multipart/form-data with images[]), list, retrieve, update, delete.
    Query params supported:
      - available=1  (only available)
      - landlord=<id> (filter by landlord id)
      - region=<id> (filter by region)
      - district=<id> (filter by district)
    """
    queryset = Property.objects.select_related('region', 'district', 'landlord')\
        .prefetch_related('images', 'facilities').all().order_by('-created_at')
    serializer_class = PropertySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]  # accept multipart/form-data

    def perform_create(self, serializer):
        """
        Let serializer handle landlord assignment (it will use request user when available).
        """
        serializer.save()

    def _parse_facilities_payload(self, payload):
        """
        Normalize incoming payload into two lists: numeric_ids (ints) and keys (strings).
        Accepts:
          - JSON string: "[1,2]" or '["wifi","gym"]'
          - Python list (from parsed JSON/form parser)
          - comma-separated string: "wifi,gym"
        Returns: (ids_list, keys_list)
        """
        import json

        if payload is None:
            return ([], [])
        fac_list = []
        # If it's already a list/tuple-like
        if isinstance(payload, (list, tuple)):
            fac_list = list(payload)
        elif isinstance(payload, str):
            payload = payload.strip()
            if not payload:
                fac_list = []
            else:
                # try parse JSON first
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, (list, tuple)):
                        fac_list = list(parsed)
                    else:
                        # something else (e.g. single string)
                        fac_list = [parsed]
                except Exception:
                    # fallback: comma separated
                    fac_list = [p.strip() for p in payload.split(",") if p.strip()]
        else:
            # other single scalar (int)
            fac_list = [payload]

        ids = []
        keys = []
        for item in fac_list:
            if item is None:
                continue
            s = str(item).strip()
            # numeric id?
            if s.isdigit():
                try:
                    ids.append(int(s))
                except Exception:
                    pass
            else:
                # treat as key/name string
                if s:
                    keys.append(s)
        return (ids, keys)

    def _attach_facilities_to_instance(self, instance, payload):
        """
        Attach facilities to `instance` based on payload.
        Payload may be JSON string, array, or comma separated keys.
        If payload is an empty list, clear facilities.
        """
        try:
            ids, keys = self._parse_facilities_payload(payload)

            # If empty list explicitly passed (and nothing else), clear set
            if isinstance(payload, (list, tuple)) and len(payload) == 0:
                instance.facilities.clear()
                return

            if ids:
                # attach by numeric ids
                qs = Facility.objects.filter(id__in=ids)
                instance.facilities.set(qs)
            elif keys:
                # prefer matching Facility.key first, fallback to name if needed
                qs = Facility.objects.filter(key__in=keys)
                if qs.exists():
                    instance.facilities.set(qs)
                else:
                    # try matching by name (case-insensitive)
                    # map incoming keys to facilities by name
                    lower_keys = [k.lower() for k in keys]
                    qs2 = Facility.objects.filter(name__iregex=r'(' + '|'.join([r'\b' + k + r'\b' for k in lower_keys]) + r')')
                    if qs2.exists():
                        instance.facilities.set(qs2)
                    else:
                        # nothing matched; attempt find by exact name/key individually
                        matched = []
                        for k in keys:
                            f = Facility.objects.filter(models.Q(key=k) | models.Q(name__iexact=k)).first()
                            if f:
                                matched.append(f.id)
                        if matched:
                            instance.facilities.set(Facility.objects.filter(id__in=matched))
                        else:
                            # nothing matched, do nothing (don't clear)
                            pass
            # else: nothing provided or could not parse => leave as-is
        except Exception as e:
            # Don't fail the request if facility parsing has an error; log for debugging.
            print("facility attach error:", e)

    def create(self, request, *args, **kwargs):
        """
        Override to support multipart image uploads (images[]).
        Also accept 'facilities' (JSON string or array) or 'facility_ids' to attach Facility m2m.
        """
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        instance = serializer.instance

        # Attach images if any (serializer.create also handles but ensure here)
        files = request.FILES.getlist('images')
        for f in files:
            PropertyImage.objects.create(property=instance, image=f)

        # Accept either 'facilities' or 'facility_ids'
        fac_payload = request.data.get('facilities', None) or request.data.get('facility_ids', None)
        if fac_payload is not None:
            self._attach_facilities_to_instance(instance, fac_payload)

        output_serializer = self.get_serializer(instance, context={'request': request})
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Ensure updates accept multipart images[] to append to existing images.
        Also accept 'facilities' (JSON string or array) or 'facility_ids' to set Facility m2m.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # handle newly uploaded images (append)
        files = request.FILES.getlist('images')
        for f in files:
            PropertyImage.objects.create(property=instance, image=f)

        # Update facilities if provided (note: allow clearing with empty list)
        if 'facilities' in request.data or 'facility_ids' in request.data:
            fac_payload = request.data.get('facilities', None) if 'facilities' in request.data else request.data.get('facility_ids', None)
            self._attach_facilities_to_instance(instance, fac_payload)

        return Response(self.get_serializer(instance, context={'request': request}).data)

    def get_queryset(self):
        qs = super().get_queryset()
        only_available = self.request.query_params.get('available')
        landlord = self.request.query_params.get('landlord')
        region = self.request.query_params.get('region')
        district = self.request.query_params.get('district')

        if only_available == '1':
            qs = qs.filter(is_available=True)
        if landlord:
            qs = qs.filter(landlord_id=landlord)
        if region:
            qs = qs.filter(region_id=region)
        if district:
            qs = qs.filter(district_id=district)

        return qs



# ================= Application ViewSet =================
class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.select_related('property', 'renter').all().order_by('-created_at')
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(renter=self.request.user)

    def get_queryset(self):
        user = self.request.user
        if user.role == 'landlord':
            # landlord sees applications for their properties
            return Application.objects.filter(property__landlord=user).order_by('-created_at')
        # renter sees applications they created
        return Application.objects.filter(renter=user).order_by('-created_at')


# ================= Message ViewSet =================
class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.select_related('sender', 'receiver').all().order_by('-created_at')
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Message.objects.filter(models.Q(sender=user) | models.Q(receiver=user)).order_by('-created_at')


# ================= Custom JWT Login View =================
# We import serializer from serializers.py; make sure CustomTokenObtainPairSerializer is defined there.
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# ================= AUTH ME ENDPOINT =================
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def auth_me(request):
    """
    Returns logged-in user profile
    """
    user = request.user
    serializer = UserSerializer(user, context={'request': request})
    return Response(serializer.data)


class BannerListView(ListAPIView):
    serializer_class = BannerSerializer

    def get_queryset(self):
        return Banner.objects.filter(is_active=True)




@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def profile_me(request):
    user = request.user

    print("---- profile_me DEBUG ----")
    print("method:", request.method)
    print("content_type:", request.content_type)
    print("FILES keys:", list(request.FILES.keys()))
    print("DATA keys:", list(request.data.keys()))

    if request.method == 'GET':
        return Response(UserSerializer(user, context={'request': request}).data)

    partial = request.method == 'PATCH'
    data = request.data.copy()

    # map name -> first_name
    if 'name' in data:
        data['first_name'] = data.pop('name')

    # 🚨 CRITICAL FIX
    if request.content_type == 'application/json':
        data.pop('avatar', None)

    # attach real file if multipart
    if 'avatar' in request.FILES:
        data['avatar'] = request.FILES['avatar']

    serializer = UserSerializer(user, data=data, partial=partial, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)

    print("serializer errors:", serializer.errors)
    return Response(serializer.errors, status=400)


# ================= Facility List View =================
class FacilityListView(generics.ListAPIView):
    """
    List all available facilities (wifi, parking, gym, etc)
    """
    queryset = Facility.objects.all().order_by('name')
    serializer_class = FacilitySerializer
    permission_classes = [permissions.AllowAny]




class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        new_password = serializer.validated_data['new_password1']
        user.set_password(new_password)
        user.save()
        # Optionally: invalidate sessions / tokens here if you want to force re-login
        return Response({'detail': 'Password changed successfully.'}, status=status.HTTP_200_OK)


# accounts/views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .serializers import DeleteAccountSerializer

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        serializer = DeleteAccountSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.delete()

        return Response(
            {"detail": "Account deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "If account exists, OTP was sent."},
                status=status.HTTP_200_OK
            )

        code = str(random.randint(100000, 999999))

        PasswordResetOTP.objects.create(user=user, code=code)

        send_mail(
            subject="Your password reset code",
            message=f"Your password reset code is: {code}",
            from_email=None,
            recipient_list=[email],
        )

        return Response({"detail": "OTP sent to email"}, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        code = serializer.validated_data['code']

        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')
        except:
            return Response({"detail": "Invalid code"}, status=400)

        if otp.is_expired():
            return Response({"detail": "Code expired"}, status=400)

        return Response({"detail": "Code verified"}, status=200)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        code = serializer.validated_data['code']
        new_password = serializer.validated_data['new_password']

        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')
        except:
            return Response({"detail": "Invalid request"}, status=400)

        if otp.is_expired():
            return Response({"detail": "Code expired"}, status=400)

        user.set_password(new_password)
        user.save()

        otp.is_used = True
        otp.save()

        return Response({"detail": "Password reset successful"}, status=200)


# core/views.py (ADD THESE)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Notification, UserNotification
from .serializers import NotificationSerializer


class NotificationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(is_active=True)
        data = []
        for n in notifications:
            un, _ = UserNotification.objects.get_or_create(
                user=request.user,
                notification=n
            )
            data.append({
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "created_at": n.created_at,
                "read": un.read,
            })
        return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    un, _ = UserNotification.objects.get_or_create(
        user=request.user,
        notification=notification
    )
    un.read = True
    un.read_at = timezone.now()
    un.save()
    return Response({"detail": "marked read"})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    notifications = Notification.objects.filter(is_active=True)
    for n in notifications:
        un, _ = UserNotification.objects.get_or_create(
            user=request.user,
            notification=n
        )
        un.read = True
        un.read_at = timezone.now()
        un.save()
    return Response({"detail": "all marked read"})
