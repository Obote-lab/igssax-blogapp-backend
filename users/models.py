from django.contrib.auth.models import (AbstractBaseUser, BaseUserManager,
                                        PermissionsMixin)
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier"""

    use_in_migrations = True

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_verified", False)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("status", User.Status.ACTIVE)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        BANNED = "banned", _("Banned")
        SUSPENDED = "suspended", _("Suspended")

    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(_("first name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100, blank=True)
    username = models.CharField(
        _("username"), max_length=100, unique=True, blank=True, null=True
    )
    phone_number = models.CharField(
        _("phone number"), max_length=20, blank=True, null=True
    )
    is_verified = models.BooleanField(_("verified account"), default=False)
    last_login_ip = models.GenericIPAddressField(
        _("last login IP"), null=True, blank=True
    )
    last_seen = models.DateTimeField(_("last seen"), null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    is_superuser = models.BooleanField(_("superuser status"), default=False)
    date_joined = models.DateTimeField(_("date joined"), auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    # Follow helpers
    def follow(self, user):
        from .models import Follow

        if self != user and not self.is_following(user):
            Follow.objects.create(follower=self, following=user)
            return True
        return False

    def unfollow(self, user):
        from .models import Follow

        Follow.objects.filter(follower=self, following=user).delete()
        return True

    def is_following(self, user):
        return self.following.filter(following=user).exists()

    def is_followed_by(self, user):
        return self.followers.filter(follower=user).exists()

        # Friends helpers

    def send_friend_request(self, user):
        from .models import Friendship

        if (
            self != user
            and not Friendship.objects.filter(requester=self, receiver=user).exists()
        ):
            Friendship.objects.create(requester=self, receiver=user)
            return True
        return False

    def get_friends(self):
        from .models import Friendship

        return User.objects.filter(
            id__in=Friendship.objects.filter(
                (models.Q(requester=self) | models.Q(receiver=self)),
                status=Friendship.Status.ACCEPTED,
            ).values_list("requester", "receiver")
        ).exclude(id=self.id)


class Friendship(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")

    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="friend_requests_sent"
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="friend_requests_received"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("requester", "receiver")

    def __str__(self):
        return f"{self.requester.email} -> {self.receiver.email} ({self.status})"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(_("bio"), blank=True)
    location = models.CharField(_("location"), max_length=100, blank=True)
    birth_date = models.DateField(_("birth date"), null=True, blank=True)

    gender = models.CharField(
        _("gender"),
        max_length=10,
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        blank=True,
    )

    website = models.URLField(_("website"), blank=True, null=True)
    avatar = models.ImageField(_("avatar"), upload_to="avatars/", null=True, blank=True)
    cover_photo = models.ImageField(
        _("cover photo"), upload_to="covers/", null=True, blank=True
    )

    # Extra social fields
    work = models.CharField(_("work"), max_length=100, blank=True)
    education = models.CharField(_("education"), max_length=100, blank=True)
    relationship_status = models.CharField(
        _("relationship status"),
        max_length=20,
        choices=[
            ("single", "Single"),
            ("in_relationship", "In a relationship"),
            ("married", "Married"),
            ("complicated", "It’s complicated"),
        ],
        blank=True,
    )
    interests = models.TextField(_("interests"), blank=True)
    hobbies = models.TextField(_("hobbies"), blank=True)

    # Stats
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)
    friends_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    def __str__(self):
        return f"{self.user.email} Profile"


class Follow(models.Model):
    follower = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="following"
    )
    following = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="followers"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("follower", "following")

    def __str__(self):
        return f"{self.follower.email} follows {self.following.email}"


class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    profile_visibility = models.CharField(max_length=20,choices=[("public", "Public"), ("friends", "Friends"), ("private", "Private")],default="public", )
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    newsletter = models.BooleanField(default=False)

    # Display
    theme = models.CharField(max_length=20, choices=[("light", "Light"), ("dark", "Dark")], default="light")
    language = models.CharField(max_length=10, default="en")

    # Security
    two_factor_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.user.email}"
