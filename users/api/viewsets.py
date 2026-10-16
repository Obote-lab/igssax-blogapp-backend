import logging

import requests
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import UpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from ..models import (BlockedUser, Follow, Friendship, Profile, User,
                      UserSettings)
from ..utils import build_token_response
from .serializers import (AccountUpdateSerializer, BlockedUserSerializer,
                          BlockUserSerializer, ChangePasswordSerializer,
                          CustomPasswordResetConfirmSerializer,
                          CustomPasswordResetRequestSerializer,
                          FriendshipSerializer, GoogleSignUpSerializer,
                          PrivacySettingsSerializer, UserListSerializer,
                          UserProfileSerializer, UserRegisterSerializer,
                          UserSerializer, UserSettingsSerializer)

logger = logging.getLogger(__name__)
User = get_user_model()


# JWT Token with extra fields
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        super().validate(attrs)

        data = build_token_response(self.user)

        data["email"] = self.user.email
        try:
            data["name"] = self.user.profile.bio or ""
            data["profile_pic"] = (
                self.user.profile.avatar.url if self.user.profile.avatar else ""
            )
        except Exception:
            data["name"] = ""
            data["profile_pic"] = ""

        return data


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# User ViewSet
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for browsing user profiles."""

    # queryset = User.objects.all().select_related("profile").order_by("id")
    queryset = (
        User.objects.select_related("profile", "settings")
        .filter(status=User.Status.ACTIVE)
        .order_by("id")
    )
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    # def get_queryset(self):
    #     return self.queryset.filter(status=User.Status.ACTIVE)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def friends(self, request, pk=None):
        user = self.get_object()

        friends = (
            User.objects.filter(
                Q(
                    friendships_sent__receiver=user,
                    friendships_sent__status=Friendship.Status.ACCEPTED,
                )
                | Q(
                    friendships_received__requester=user,
                    friendships_received__status=Friendship.Status.ACCEPTED,
                )
            )
            .select_related("profile")
            .distinct()
        )

        return Response(
            UserListSerializer(friends, many=True, context={"request": request}).data
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def pending_requests_sent(self, request, pk=None):
        user = self.get_object()
        requests_sent = Friendship.objects.filter(
            requester=user, status=Friendship.Status.PENDING
        ).select_related("receiver")
        receivers = [f.receiver for f in requests_sent]
        return Response(
            UserListSerializer(receivers, many=True, context={"request": request}).data
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def pending_requests_received(self, request, pk=None):
        user = self.get_object()
        requests_received = Friendship.objects.filter(
            receiver=user, status=Friendship.Status.PENDING
        ).select_related("requester")
        requesters = [f.requester for f in requests_received]
        return Response(
            UserListSerializer(requesters, many=True, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def block(self, request, pk=None):
        user_to_block = self.get_object()
        if user_to_block == request.user:
            return Response(
                {"error": "You cannot block yourself"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        Friendship.objects.filter(
            Q(requester=request.user, receiver=user_to_block)
            | Q(requester=user_to_block, receiver=request.user)
        ).delete()
        Follow.objects.filter(
            Q(follower=request.user, following=user_to_block)
            | Q(follower=user_to_block, following=request.user)
        ).delete()
        BlockedUser.objects.get_or_create(blocker=request.user, blocked=user_to_block)
        return Response({"success": "User blocked successfully"})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def unblock(self, request, pk=None):
        user_to_unblock = self.get_object()
        try:
            blocked_user = BlockedUser.objects.get(
                blocker=request.user, blocked=user_to_unblock
            )
            blocked_user.delete()
            return Response({"success": "User unblocked successfully"})
        except BlockedUser.DoesNotExist:
            return Response(
                {"error": "User is not blocked"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def blocked_users(self, request):
        blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related(
            "blocked"
        )
        serializer = BlockedUserSerializer(blocked_users, many=True)
        return Response(serializer.data)

    # Custom endpoints
    @action(
        detail=False,
        methods=["get"],
        url_path="friends/suggestions",
        permission_classes=[IsAuthenticated],
    )
    def friends_suggestions(self, request):
        # suggestions = User.objects.exclude(id=request.user.id)[:10]
        suggestions = User.objects.exclude(
            Q(id=request.user.id)
            | Q(blocked_by__blocker=request.user)
            | Q(blocked_users__blocked=request.user)
        )[:10]
        return Response(
            UserListSerializer(
                suggestions, many=True, context={"request": request}
            ).data
        )

    @action(detail=False, methods=["get"], url_path="recent-active")
    def recent_active(self, request):
        recent = User.objects.filter(last_seen__isnull=False).order_by("-last_seen")[
            :10
        ]
        return Response(
            UserListSerializer(recent, many=True, context={"request": request}).data
        )

    @action(detail=False, methods=["get"], url_path="trending")
    def trending(self, request):
        # trending = User.objects.order_by("-profile__followers_count")[:10]
        trending = User.objects.select_related("profile").order_by(
            "-profile__followers_count"
        )[:10]
        return Response(
            UserListSerializer(trending, many=True, context={"request": request}).data
        )


# Register API
class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = UserRegisterSerializer

    def post(self, request):
        serializer = UserRegisterSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token_data = build_token_response(user)

        return Response(
            {
                **token_data,
                "user": UserSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


# Account Update API
class AccountUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccountUpdateSerializer

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def update_user(self, request, partial=False):
        serializer = AccountUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user, context={"request": request}).data)

    def put(self, request):
        return self.update_user(request, partial=False)

    def patch(self, request):
        return self.update_user(request, partial=True)


# Profile Update API
class UserProfileUpdate(UpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.profile


# Friendship ViewSet
class FriendshipViewSet(viewsets.ModelViewSet):
    queryset = Friendship.objects.none()
    serializer_class = FriendshipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Friendship.objects.none()

        return Friendship.objects.filter(
            Q(requester=self.request.user) | Q(receiver=self.request.user)
        )

    def create(self, request, *args, **kwargs):
        receiver_id = request.data.get("receiver")

        if not receiver_id or int(receiver_id) == request.user.id:
            return Response({"error": "Invalid receiver"}, status=400)

        try:
            receiver = User.objects.get(id=receiver_id)
        except User.DoesNotExist:
            return Response({"error": "Receiver not found"}, status=404)

        if Friendship.objects.filter(
            Q(requester=request.user, receiver=receiver)
            | Q(requester=receiver, receiver=request.user)
        ).exists():
            return Response({"error": "Friendship already exists"}, status=400)

        friendship = Friendship.objects.create(
            requester=request.user, receiver=receiver, status=Friendship.Status.PENDING
        )

        return Response(
            FriendshipSerializer(friendship).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        friendship = self.get_object()
        if friendship.receiver != request.user:
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        friendship._previous_status = friendship.status
        friendship.status = Friendship.Status.ACCEPTED
        friendship.save()
        return Response({"success": "Friend request accepted"})

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        friendship = self.get_object()
        if friendship.receiver != request.user:
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        friendship._previous_status = friendship.status
        friendship.status = Friendship.Status.REJECTED
        friendship.save()
        return Response({"success": "Friend request rejected"})


# Password Change API
class PasswordChange(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password changed successfully"})


# Google OAuth APIs
class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    permission_classes = [AllowAny]


class GoogleSignUpView(APIView):
    permission_classes = [AllowAny]
    serializer_class = GoogleSignUpSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        access_token = serializer.validated_data["access_token"]

        try:
            user_info = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            ).json()

            email = user_info.get("email")
            name = user_info.get("name", "")
            picture = user_info.get("picture", "")

            if not email:
                return Response({"error": "Email not returned by Google"}, status=400)

            user, created = User.objects.get_or_create(email=email)
            if created:
                user.set_unusable_password()
                user.save()

            profile = user.profile
            if picture and not profile.avatar:
                img = requests.get(picture)
                if img.status_code == 200:
                    profile.avatar.save(
                        f"{user.id}_google.jpg",
                        ContentFile(img.content),
                        save=True,
                    )

            token_data = build_token_response(user)

            return Response(
                {
                    **token_data,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": name,
                        "profile_pic": picture,
                        "is_new_user": created,
                    },
                },
                status=200,
            )

        except requests.RequestException as e:
            return Response({"error": f"Google API error: {e}"}, status=500)


# Password Reset APIs
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    serializer_class = CustomPasswordResetRequestSerializer

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email is required"}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "No user found with this email"}, status=404)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        current_site = get_current_site(request)
        frontend_url = getattr(
            settings, "FRONTEND_URL", f"http://{current_site.domain}"
        )
        reset_link = f"{frontend_url}/reset-password/{uid}/{token}/"

        send_mail(
            "IGSSAX Password Reset",
            f"Hi {user.first_name},\n\nClick here to reset your password:\n{reset_link}",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        return Response({"message": "Password reset email sent"}, status=200)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    serializer_class = CustomPasswordResetConfirmSerializer

    def post(self, request, uidb64, token):
        serializer = CustomPasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data["new_password"]

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid link"}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired token"}, status=400)

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password has been reset successfully"}, status=200)


# Blocked Users ViewSet
class BlockedUsersViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BlockedUserSerializer
    lookup_field = "id"

    def list(self, request):
        blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related(
            "blocked"
        )
        serializer = BlockedUserSerializer(blocked_users, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = BlockUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_to_block_id = serializer.validated_data["user_id"]
        reason = serializer.validated_data.get("reason", "")

        if user_to_block_id == request.user.id:
            return Response({"error": "Cannot block yourself"}, status=400)

        user_to_block = User.objects.get(id=user_to_block_id)
        BlockedUser.objects.get_or_create(
            blocker=request.user, blocked=user_to_block, reason=reason
        )

        Friendship.objects.filter(
            Q(requester=request.user, receiver=user_to_block)
            | Q(requester=user_to_block, receiver=request.user)
        ).delete()

        Follow.objects.filter(
            Q(follower=request.user, following=user_to_block)
            | Q(follower=user_to_block, following=request.user)
        ).delete()

        return Response(
            {
                "success": "User blocked successfully",
                "blocked_user_id": user_to_block_id,
            },
            status=201,
        )

    @extend_schema(parameters=[OpenApiParameter("id", int, OpenApiParameter.PATH)])
    def destroy(self, request, id=None):
        try:
            blocked_user = BlockedUser.objects.get(blocker=request.user, blocked_id=id)
            blocked_user.delete()
            return Response({"success": "User unblocked successfully"})
        except BlockedUser.DoesNotExist:
            return Response({"error": "User is not blocked"}, status=404)


# Settings ViewSet
class SettingsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSettingsSerializer

    def retrieve(self, request):
        settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)
        serializer = UserSettingsSerializer(settings_obj)
        return Response(serializer.data)

    def partial_update(self, request):
        settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)
        serializer = UserSettingsSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# Privacy Settings API
class PrivacySettingsView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrivacySettingsSerializer

    def get(self, request):
        settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)
        serializer = PrivacySettingsSerializer(settings_obj)
        return Response(serializer.data)

    def patch(self, request):
        settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)
        serializer = PrivacySettingsSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"success": "Privacy settings updated", "data": serializer.data}
        )
