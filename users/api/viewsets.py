import logging
import requests
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import UpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from ..models import Friendship, Profile, User, UserSettings,BlockedUser
from .serializers import (ChangePasswordSerializer,
                          CustomPasswordResetConfirmSerializer,
                          CustomPasswordResetRequestSerializer,
                          FriendshipSerializer, GoogleSignUpSerializer,
                          UserProfileSerializer, UserRegisterSerializer,
                          UserSerializer, UserSerializerWithToken,
                          UserSettingsSerializer, AccountUpdateSerializer,
                          PrivacySettingsSerializer, BlockedUserSerializer,
                          BlockUserSerializer)

logger = logging.getLogger(__name__)
User = get_user_model()


# JWT Token with extra fields
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        data["token_expiry"] = refresh.access_token.lifetime
        data["refresh_expiry"] = refresh.lifetime
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

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Viewset for browsing user profiles.
    - /api/users/        → list all users
    - /api/users/<id>/   → get profile by user ID
    - /api/users/me/     → get current logged in user's profile
    """

    queryset = User.objects.all().select_related("profile").order_by("id")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # Optionally filter out suspended/banned users
        return self.queryset.filter(status=User.Status.ACTIVE)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        Profile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(
        detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def friends(self, request, pk=None):
        """Return all accepted friends for this user"""
        try:
            user = self.get_object()
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        # Get friendships where status=ACCEPTED
        friendships = Friendship.objects.filter(
            Q(requester=user, status=Friendship.Status.ACCEPTED)
            | Q(receiver=user, status=Friendship.Status.ACCEPTED)
        )

        # Collect friend users
        friend_ids = [
            f.requester.id if f.receiver == user else f.receiver.id for f in friendships
        ]
        friends = User.objects.filter(id__in=friend_ids).select_related("profile")

        return Response(
            UserSerializer(friends, many=True, context={"request": request}).data
        )

    @action(
        detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def pending_requests_sent(self, request, pk=None):
        """Friend requests this user has sent but are still pending"""
        user = self.get_object()
        requests_sent = Friendship.objects.filter(
            requester=user, status=Friendship.Status.PENDING
        ).select_related("receiver")
        receivers = [f.receiver for f in requests_sent]
        return Response(
            UserSerializer(receivers, many=True, context={"request": request}).data
        )

    @action(
        detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def pending_requests_received(self, request, pk=None):
        """Friend requests this user has received but are still pending"""
        user = self.get_object()
        requests_received = Friendship.objects.filter(
            receiver=user, status=Friendship.Status.PENDING
        ).select_related("requester")
        requesters = [f.requester for f in requests_received]
        return Response(
            UserSerializer(requesters, many=True, context={"request": request}).data
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def block(self, request, pk=None):
        """Block a specific user"""
        user_to_block = self.get_object()
        
        if user_to_block == request.user:
            return Response(
                {"error": "You cannot block yourself"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if already blocked
        if BlockedUser.objects.filter(blocker=request.user, blocked=user_to_block).exists():
            return Response(
                {"error": "User is already blocked"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create block
        BlockedUser.objects.create(blocker=request.user, blocked=user_to_block)
        
        # Clean up relationships
        Friendship.objects.filter(
            Q(requester=request.user, receiver=user_to_block) |
            Q(requester=user_to_block, receiver=request.user)
        ).delete()
        
        Follow.objects.filter(
            Q(follower=request.user, following=user_to_block) |
            Q(follower=user_to_block, following=request.user)
        ).delete()
        
        return Response({"success": "User blocked successfully"})
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def unblock(self, request, pk=None):
        """Unblock a specific user"""
        user_to_unblock = self.get_object()
        
        try:
            blocked_user = BlockedUser.objects.get(blocker=request.user, blocked=user_to_unblock)
            blocked_user.delete()
            return Response({"success": "User unblocked successfully"})
        except BlockedUser.DoesNotExist:
            return Response(
                {"error": "User is not blocked"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def blocked_users(self, request):
        """Get current user's blocked users list"""
        blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related('blocked')
        serializer = BlockedUserSerializer(blocked_users, many=True)
        return Response(serializer.data)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = UserRegisterSerializer
    authentication_classes = []

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                UserSerializerWithToken(user).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class AccountUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def update_user(self, request, partial=False):
        serializer = AccountUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=partial,
            context={"request": request}
        )
        if serializer.is_valid():
            user = serializer.save()
            # Return updated user with nested profile
            return Response(UserSerializer(user, context={"request": request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        return self.update_user(request, partial=False)

    def patch(self, request):
        return self.update_user(request, partial=True)



class UserProfileUpdate(UpdateAPIView):
    """Update the authenticated user's profile"""

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.profile

class FriendshipViewSet(viewsets.ModelViewSet):
    queryset = Friendship.objects.all()
    serializer_class = FriendshipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Friendship.objects.filter(Q(requester=user) | Q(receiver=user))

    def create(self, request, *args, **kwargs):
        receiver_id = request.data.get("receiver")
        if not receiver_id:
            return Response({"error": "Receiver required"}, status=400)

        if int(receiver_id) == request.user.id:
            return Response(
                {"error": "Cannot send friend request to yourself"}, status=400
            )

        if Friendship.objects.filter(
            requester=request.user, receiver_id=receiver_id
        ).exists():
            return Response({"error": "Request already sent"}, status=400)

        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        friendship = self.get_object()
        if friendship.receiver != request.user:
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        friendship.status = Friendship.Status.ACCEPTED
        friendship.save()
        return Response({"success": "Friend request accepted"})

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        friendship = self.get_object()
        if friendship.receiver != request.user:
            return Response({"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        friendship.status = Friendship.Status.REJECTED
        friendship.save()
        return Response({"success": "Friend request rejected"})


# Change Password
class PasswordChange(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        user = request.user
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            new_password = serializer.validated_data.get("new_password")
            new_password_confirm = serializer.validated_data.get("new_password2")
            if new_password and new_password == new_password_confirm:
                user.set_password(new_password)
                user.save()
                return Response({"detail": "Password changed successfully"}, status=200)
            return Response({"detail": "Passwords do not match"}, status=400)
        return Response(serializer.errors, status=400)


# Google OAuth2 Login and SignUp
class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    permission_classes = [AllowAny]


class GoogleSignUpView(APIView):
    """
    Register or login a user via Google OAuth access token.
    The frontend should POST: {"access_token": "<google_token>"}
    """

    permission_classes = [AllowAny]
    serializer_class = GoogleSignUpSerializer

    def post(self, request, *args, **kwargs):
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

            # Create or update user
            user, created = User.objects.get_or_create(email=email)
            if created:
                user.set_unusable_password()
                user.save()
                Profile.objects.create(user=user, bio=name)

            # Update profile picture if empty
            profile = user.profile
            if picture and not profile.avatar:
                profile.avatar = picture
                profile.save()

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            response_data = {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": name,
                    "profile_pic": picture,
                    "is_new_user": created,
                },
            }
            return Response(response_data, status=200)

        except requests.RequestException as e:
            return Response({"error": f"Google API error: {e}"}, status=500)


# Password Reset Request
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

        # generate token + uid
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_link = f"http://localhost:5173/reset-password/{uid}/{token}/"

        # send email
        send_mail(
            "IGSSAX Password Reset",
            f"Hi {user.first_name},\n\nClick the link below to reset your password:\n{reset_link}\n\nIf you did not request this, please ignore.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )

        return Response({"message": "Password reset email sent"}, status=200)


# Password Reset Confirm
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    serializer_class = CustomPasswordResetConfirmSerializer

    def post(self, request, uidb64, token):
        # new_password = request.data.get("password")
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data["new_password"]

        if not new_password:
            return Response({"error": "Password is required"}, status=400)

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

class BlockedUsersViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get list of users blocked by current user"""
        blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related('blocked')
        serializer = BlockedUserSerializer(blocked_users, many=True)
        return Response(serializer.data)
    
    def create(self, request):
        """Block a user"""
        serializer = BlockUserSerializer(data=request.data)
        if serializer.is_valid():
            user_to_block_id = serializer.validated_data['user_id']
            reason = serializer.validated_data.get('reason', '')
            
            # Prevent self-blocking
            if user_to_block_id == request.user.id:
                return Response(
                    {"error": "You cannot block yourself"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user_to_block = User.objects.get(id=user_to_block_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if already blocked
            if BlockedUser.objects.filter(blocker=request.user, blocked=user_to_block).exists():
                return Response(
                    {"error": "User is already blocked"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create block relationship
            blocked_user = BlockedUser.objects.create(
                blocker=request.user,
                blocked=user_to_block,
                reason=reason
            )
            
            # Remove any existing friendships or follows
            Friendship.objects.filter(
                Q(requester=request.user, receiver=user_to_block) |
                Q(requester=user_to_block, receiver=request.user)
            ).delete()
            
            Follow.objects.filter(
                Q(follower=request.user, following=user_to_block) |
                Q(follower=user_to_block, following=request.user)
            ).delete()
            
            return Response(
                {"success": "User blocked successfully", "blocked_user_id": user_to_block_id},
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, pk=None):
        """Unblock a user"""
        try:
            blocked_user = BlockedUser.objects.get(blocker=request.user, blocked_id=pk)
            blocked_user.delete()
            return Response({"success": "User unblocked successfully"})
        except BlockedUser.DoesNotExist:
            return Response(
                {"error": "User is not blocked"}, 
                status=status.HTTP_404_NOT_FOUND
            )


# Update SettingsViewSet to handle all settings
class SettingsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def retrieve(self, request):
        """Get all user settings"""
        settings, created = UserSettings.objects.get_or_create(user=request.user)
        serializer = UserSettingsSerializer(settings)
        return Response(serializer.data)

    def partial_update(self, request):
        """Update user settings"""
        settings, created = UserSettings.objects.get_or_create(user=request.user)
        serializer = UserSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    

class PrivacySettingsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's privacy settings"""
        try:
            # Ensure settings exist
            settings, created = UserSettings.objects.get_or_create(user=request.user)
            serializer = PrivacySettingsSerializer(settings)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching privacy settings: {e}")
            return Response(
                {"error": "Failed to fetch privacy settings"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def patch(self, request):
        """Update user's privacy settings"""
        try:
            settings = request.user.settings
            serializer = PrivacySettingsSerializer(
                settings, 
                data=request.data, 
                partial=True,
                context={'request': request}
            )
            
            if serializer.is_valid():
                serializer.save()
                return Response({
                    "success": "Privacy settings updated successfully",
                    "data": serializer.data
                })
            
            return Response(
                {"error": "Invalid data", "details": serializer.errors}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            logger.error(f"Error updating privacy settings: {e}")
            return Response(
                {"error": "Failed to update privacy settings"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )