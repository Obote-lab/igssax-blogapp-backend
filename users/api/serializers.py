from dj_rest_auth.registration.serializers import RegisterSerializer
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.hashers import check_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from comments.api.serializers import CommentSerializer
from comments.models import Comment

from ..models import Follow, Friendship, Profile, User, UserSettings

User = get_user_model()


class ProfileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "user",
            "bio",
            "location",
            "birth_date",
            "gender",
            "website",
            "avatar",
            "cover_photo",
            "followers_count",
            "following_count",
            "created_at",
            "updated_at",
        ]


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    avatar = serializers.ImageField(source="profile.avatar", read_only=True)
    full_name = serializers.SerializerMethodField()
    is_friend = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "username",
            "full_name",
            "phone_number",
            "is_verified",
            "last_login_ip",
            "last_seen",
            "status",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "profile",
            "avatar",
            "is_friend",
            "is_following",
            "comments",
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_is_friend(self, obj):
        request = self.context.get("request")
        if not request or request.user.is_anonymous:
            return False
        return Friendship.objects.filter(
            (
                Q(requester=request.user, receiver=obj)
                | Q(receiver=request.user, requester=obj)
            ),
            status=Friendship.Status.ACCEPTED,
        ).exists()

    def get_is_following(self, obj):
        request = self.context.get("request")
        if not request or request.user.is_anonymous:
            return False
        return Follow.objects.filter(follower=request.user, following=obj).exists()

    def get_comments(self, obj):
        request = self.context.get("request")
        comments = Comment.objects.filter(author=obj).order_by("-created_at")[:5]
        return CommentSerializer(comments, many=True, context={"request": request}).data


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = [
            "profile_visibility",
            "email_notifications",
            "push_notifications",
            "newsletter",
            "dark_mode",
            "language",
            "two_factor_enabled",
        ]


class FollowSerializer(serializers.ModelSerializer):
    """Serializer for following system"""

    follower = serializers.StringRelatedField()
    following = serializers.StringRelatedField()

    class Meta:
        model = Follow
        fields = ["id", "follower", "following", "created_at"]


class UserSerializerWithToken(UserSerializer):
    """Return user data with JWT token"""

    token = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["token"]

    def get_token(self, obj):
        refresh = RefreshToken.for_user(obj)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class UserRegisterSerializer(serializers.ModelSerializer):
    """Registration serializer"""

    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password"]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Account already exists with this email.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile updates"""

    first_name = serializers.CharField(source="user.first_name", required=False)
    last_name = serializers.CharField(source="user.last_name", required=False)

    class Meta:
        model = Profile
        fields = ["bio", "location", "birth_date", "avatar", "first_name", "last_name"]

    def update(self, instance, validated_data):
        # Pop user-related fields
        user_data = validated_data.pop("user", {})

        # Update profile fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update user fields
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()

        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    new_password2 = serializers.CharField(required=True)

    def validate(self, data):
        user = self.context["request"].user
        if not check_password(data["old_password"], user.password):
            raise serializers.ValidationError(
                {"old_password": "Old password is incorrect"}
            )
        if data["new_password"] != data["new_password2"]:
            raise serializers.ValidationError(
                {"new_password2": "Passwords do not match"}
            )
        password_validation.validate_password(data["new_password"], user)
        return data


class GoogleSignUpSerializer(serializers.Serializer):
    access_token = serializers.CharField(
        required=True,
        help_text="Google OAuth access token obtained from Google Sign In",
    )


class GoogleLoginSuccessSerializer(serializers.Serializer):
    """Serializer for Google login response"""

    user = UserSerializerWithToken()
    google_id = serializers.CharField()


class CustomRegisterSerializer(RegisterSerializer):
    username = None
    email = serializers.EmailField(required=True)


class CustomPasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class CustomPasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField()


class FriendshipSerializer(serializers.ModelSerializer):
    requester = serializers.StringRelatedField()
    receiver = serializers.StringRelatedField()

    class Meta:
        model = Friendship
        fields = ["id", "requester", "receiver", "status", "created_at"]
