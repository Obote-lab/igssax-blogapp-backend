from dj_rest_auth.registration.serializers import RegisterSerializer
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.hashers import check_password
from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from comments.api.serializers import CommentSerializer
from comments.models import Comment

from ..models import (BlockedUser, Follow, Friendship, Profile, User,
                      UserSettings)

User = get_user_model()


# Profile & Settings
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
            "friends_count",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "followers_count",
            "following_count",
            "friends_count",
        ]


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = "__all__"
        read_only_fields = ["user", "created_at", "updated_at"]


# Main User Serializer
class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    settings = UserSettingsSerializer(read_only=True)
    avatar = serializers.ImageField(source="profile.avatar", read_only=True)
    full_name = serializers.SerializerMethodField()
    is_friend = serializers.SerializerMethodField(required=False)
    is_following = serializers.SerializerMethodField(required=False)
    comments = serializers.SerializerMethodField(required=False)

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
            # "is_staff", "is_superuser",
            "date_joined",
            "profile",
            "avatar",
            "is_friend",
            "is_following",
            "comments",
            "settings",
        ]

    def _get_request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()

    @extend_schema_field(serializers.BooleanField)
    def get_is_friend(self, obj) -> bool:
        user = self._get_request_user()
        if not user or user.is_anonymous or user == obj:
            return False

        return (
            getattr(obj, "_is_friend", None)
            or Friendship.objects.filter(
                Q(requester=user, receiver=obj) | Q(receiver=user, requester=obj),
                status=Friendship.Status.ACCEPTED,
            ).exists()
        )

    @extend_schema_field(serializers.BooleanField)
    def get_is_following(self, obj) -> bool:
        user = self._get_request_user()
        if not user or user.is_anonymous or user == obj:
            return False

        return (
            getattr(obj, "_is_following", None)
            or Follow.objects.filter(follower=user, following=obj).exists()
        )

    @extend_schema_field(CommentSerializer(many=True))
    def get_comments(self, obj) -> list:
        request = self.context.get("request")
        if not request or request.user.is_anonymous:
            return []

        if BlockedUser.objects.filter(blocker=obj, blocked=request.user).exists():
            return []

        comments = (
            Comment.objects.filter(author=obj)
            .select_related("post")
            .order_by("-created_at")[:5]
        )
        return CommentSerializer(comments, many=True, context=self.context).data


class UserListSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(source="profile.avatar", read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "avatar"]

    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()


class UserSerializerWithToken(UserSerializer):
    token = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["token"]

    @extend_schema_field(serializers.DictField)
    def get_token(self, obj) -> dict:
        refresh = RefreshToken.for_user(obj)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "access_expires": int(refresh.access_token.lifetime.total_seconds()),
            "refresh_expires": int(refresh.lifetime.total_seconds()),
        }


# Account Update Serializer
class AccountUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    avatar = serializers.ImageField(required=False, allow_empty_file=True)
    cover_photo = serializers.ImageField(required=False, allow_empty_file=True)

    # Profile fields
    bio = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)
    work = serializers.CharField(required=False, allow_blank=True)
    education = serializers.CharField(required=False, allow_blank=True)
    relationship_status = serializers.CharField(required=False, allow_blank=True)
    interests = serializers.CharField(required=False, allow_blank=True)
    hobbies = serializers.CharField(required=False, allow_blank=True)

    # Security
    current_password = serializers.CharField(write_only=True, required=False)
    new_password = serializers.CharField(write_only=True, required=False)

    def validate(self, data):
        user = self.context["request"].user

        # Password change validation
        if "new_password" in data:
            if "current_password" not in data:
                raise serializers.ValidationError(
                    {"current_password": "Current password is required."}
                )
            if not check_password(data["current_password"], user.password):
                raise serializers.ValidationError(
                    {"current_password": "Current password is incorrect."}
                )
            password_validation.validate_password(data["new_password"], user)

        return data

    def update(self, instance, validated_data):
        profile = instance.profile

        for field in ["first_name", "last_name", "email", "username", "phone_number"]:
            if field in validated_data:
                if (
                    field == "email"
                    and User.objects.exclude(id=instance.id)
                    .filter(email=validated_data["email"])
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {"email": "Email already in use."}
                    )
                if (
                    field == "username"
                    and User.objects.exclude(id=instance.id)
                    .filter(username=validated_data["username"])
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {"username": "Username already taken."}
                    )
                setattr(instance, field, validated_data[field])

        # Update Profile fields
        for field in [
            "bio",
            "location",
            "birth_date",
            "gender",
            "website",
            "avatar",
            "cover_photo",
            "work",
            "education",
            "relationship_status",
            "interests",
            "hobbies",
        ]:
            if field in validated_data:
                setattr(profile, field, validated_data[field])

        if "new_password" in validated_data:
            instance.set_password(validated_data["new_password"])
            instance.last_login = None

        instance.save()
        profile.save()
        return instance


# Follow / Friendship / Blocked
class FollowSerializer(serializers.ModelSerializer):
    follower = serializers.IntegerField(source="follower.id", read_only=True)
    following = serializers.IntegerField(source="following.id", read_only=True)

    class Meta:
        model = Follow
        fields = ["id", "follower", "following", "created_at"]


class FollowCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()

    def validate_user_id(self, value):
        user = self.context["request"].user
        if user.id == value:
            raise serializers.ValidationError("You cannot follow yourself.")
        if Follow.objects.filter(follower=user, following_id=value).exists():
            raise serializers.ValidationError("Already following.")
        return value


class FriendshipSerializer(serializers.ModelSerializer):
    requester = serializers.StringRelatedField()
    receiver = serializers.StringRelatedField()
    user_id = serializers.IntegerField()

    class Meta:
        model = Friendship
        fields = ["id", "requester", "receiver", "status", "created_at", "user_id"]

    def validate_user_id(self, value):
        user = self.context["request"].user
        if user.id == value:
            raise serializers.ValidationError("You cannot friend yourself.")
        if Friendship.objects.filter(
            Q(requester=user, receiver_id=value) | Q(receiver=user, requester_id=value)
        ).exists():
            raise serializers.ValidationError("Friend request already exists.")
        return value


class BlockedUserSerializer(serializers.ModelSerializer):
    blocked_user_id = serializers.IntegerField(source="blocked.id")
    blocked_user_email = serializers.EmailField(source="blocked.email")
    blocked_user_name = serializers.SerializerMethodField()

    class Meta:
        model = BlockedUser
        fields = [
            "id",
            "blocked_user_id",
            "blocked_user_email",
            "blocked_user_name",
            "created_at",
            "reason",
        ]
        read_only_fields = ["id", "created_at"]

    @extend_schema_field(serializers.CharField)
    def get_blocked_user_name(self, obj) -> str:
        return f"{obj.blocked.first_name} {obj.blocked.last_name}".strip()


class BlockUserSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found")
        return value


# Google OAuth Serializers
class GoogleSignUpSerializer(serializers.Serializer):
    access_token = serializers.CharField(required=True)


class GoogleLoginSuccessSerializer(serializers.Serializer):
    user = UserSerializerWithToken()
    google_id = serializers.CharField()


# DJ-Rest-Auth Custom Register
class CustomRegisterSerializer(RegisterSerializer):
    username = None
    email = serializers.EmailField(required=True)


# Change Password Serializer
class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not check_password(value, user.password):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError(
                {"new_password2": "Passwords do not match."}
            )
        password_validation.validate_password(
            attrs["new_password"], self.context["request"].user
        )
        return attrs


# Password Reset Request Serializer
class CustomPasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value


# Password Reset Confirm Serializer
class CustomPasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True)
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError(
                {"new_password2": "Passwords do not match."}
            )
        return attrs


# Privacy Settings Serializer
class PrivacySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = [
            "profile_visibility",
            "show_activity_status",
            "show_last_seen",
            "show_online_status",
            "allow_friend_requests",
            "allow_follow_requests",
            "allow_messages_from",
            "search_engine_indexing",
            "show_in_search_results",
            "default_post_visibility",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


# User Profile Serializer
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            "bio",
            "location",
            "birth_date",
            "gender",
            "website",
            "avatar",
            "cover_photo",
            "work",
            "education",
            "relationship_status",
            "interests",
            "hobbies",
        ]


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.
    Creates a user and an associated profile.
    """

    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    password2 = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    full_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "password",
            "password2",
            "full_name",
        ]

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password2", None)

        # Optionally set first_name / last_name from full_name
        full_name = validated_data.pop("full_name", "")
        if full_name:
            name_parts = full_name.strip().split(" ", 1)
            validated_data["first_name"] = name_parts[0]
            validated_data["last_name"] = name_parts[1] if len(name_parts) > 1 else ""

        # Create user
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()

        return user
