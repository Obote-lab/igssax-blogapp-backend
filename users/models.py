from django.contrib.auth.models import (AbstractBaseUser, BaseUserManager,PermissionsMixin)
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator



phone_validator = RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
)

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
    username = models.CharField(_("username"), max_length=100, blank=True, null=True)
    phone_number = models.CharField( _("phone number"), max_length=20, blank=True, null=True,validators=[phone_validator] )
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
    date_joined = models.DateTimeField(_("date joined"), auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def follow(self, user):
        if self != user and not self.is_following(user):
            Follow.objects.create(follower=self, following=user)
            return True
        return False

    def unfollow(self, user):
        Follow.objects.filter(follower=self, following=user).delete()
        return True

    def is_following(self, user):
        return self.following.filter(following=user).exists()

    def is_followed_by(self, user):
        return self.followers.filter(follower=user).exists()

    def send_friend_request(self, user):
        if self == user:
            return False
        if Friendship.objects.filter(requester=self, receiver=user).exists():
            return False
        Friendship.objects.create(requester=self, receiver=user)
        return True

    def get_friends(self):
        friendships = Friendship.objects.filter(
            models.Q(requester=self) | models.Q(receiver=self),
            status=Friendship.Status.ACCEPTED,
        )

        friend_ids = friendships.values_list("requester_id", flat=True).union(
            friendships.values_list("receiver_id", flat=True)
        )

        return User.objects.filter(id__in=friend_ids).exclude(id=self.id)

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def __str__(self):
        return self.get_full_name()

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
        # unique_together = ("requester", "receiver")
        constraints = [
            models.UniqueConstraint(
                fields=["requester", "receiver"], name="unique_friendship"
            )
        ]
        indexes = [
            models.Index(fields=["requester"]),
            models.Index(fields=["receiver"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.requester.email} -> {self.receiver.email} ({self.status})"

    def accept(self):
        self.status = Friendship.Status.ACCEPTED
        self.save(update_fields=["status"])

    def reject(self):
        self.status = Friendship.Status.REJECTED
        self.save(update_fields=["status"])


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
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    cover_photo = models.ImageField(upload_to="covers/", null=True, blank=True)

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
        # unique_together = ("follower", "following")
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"], name="unique_follow"
            )
        ]
        indexes = [
            models.Index(fields=["follower"]),
            models.Index(fields=["following"]),
        ]

    def __str__(self):
        return f"{self.follower.email} follows {self.following.email}"


class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    profile_visibility = models.CharField(
        max_length=20,
        choices=[("public", "Public"), ("friends", "Friends"), ("private", "Private")],
        default="public",
    )
    show_activity_status = models.BooleanField(default=True)
    show_last_seen = models.BooleanField(default=True)
    show_online_status = models.BooleanField(default=True)
    allow_friend_requests = models.BooleanField(default=True)
    allow_follow_requests = models.BooleanField(default=True)
    allow_messages_from = models.CharField(
        max_length=20,
        choices=[
            ("everyone", "Everyone"),
            ("friends", "Friends Only"),
            ("nobody", "Nobody"),
        ],
        default="everyone",
    )
    show_email = models.BooleanField(default=False)
    show_phone = models.BooleanField(default=False)
    last_seen_visibility = models.CharField(
        max_length=20,
        choices=[
            ("everyone", "Everyone"),
            ("friends", "Friends Only"),
            ("nobody", "Nobody"),
        ],
        default="friends",
    )
    allow_tagging = models.BooleanField(default=True)
    allow_comments = models.BooleanField(default=True)
    search_engine_indexing = models.BooleanField(default=True)
    show_in_search_results = models.BooleanField(default=True)
    default_post_visibility = models.CharField(
        max_length=20,
        choices=[
            ("public", "Public"),
            ("friends", "Friends Only"),
            ("private", "Private"),
        ],
        default="public",
    )

    # Email & Notifications
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    newsletter = models.BooleanField(default=False)

    # Display
    theme = models.CharField(
        max_length=20,
        choices=[
            ("light", "Light"),
            ("dark", "Dark"),
            ("system", "System"),
            ("blue", "Ocean"),
            ("green", "Forest"),
            ("purple", "Royal"),
        ],
        default="light",
    )
    font_size = models.PositiveIntegerField(
        default=16, help_text="Base font size in pixels"
    )
    layout_density = models.CharField(
        max_length=20,
        choices=[("comfortable", "Comfortable"), ("compact", "Compact")],
        default="comfortable",
    )

    # Accessibility Settings
    reduced_motion = models.BooleanField(
        default=False, help_text="Reduce animations and transitions"
    )
    high_contrast = models.BooleanField(
        default=False, help_text="Increase color contrast for better visibility"
    )
    color_blind_mode = models.BooleanField(
        default=False, help_text="Optimize colors for color vision deficiency"
    )

    language = models.CharField(
        max_length=10,
        choices=[
            ("en", "English"),
            ("es", "Español"),
            ("fr", "Français"),
            ("de", "Deutsch"),
            ("zh", "中文"),
        ],
        default="en",
    )

    # Security
    two_factor_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.user.email}"

    def save(self, *args, **kwargs):
        if self.font_size < 12:
            self.font_size = 12
        elif self.font_size > 20:
            self.font_size = 20
        super().save(*args, **kwargs)


class BlockedUser(models.Model):
    blocker = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="blocked_users"
    )
    blocked = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="blocked_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        verbose_name = "Blocked User"
        verbose_name_plural = "Blocked Users"
        indexes = [
            models.Index(fields=["blocker"]),
            models.Index(fields=["blocked"]),
        ]

    def __str__(self):
        return f"{self.blocker.email} blocked {self.blocked.email}"
