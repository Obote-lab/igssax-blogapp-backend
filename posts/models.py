from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Post(models.Model):
    PRIVACY_CHOICES = [
        ("public", "Public"),
        ("friends", "Friends"),
        ("only_me", "Only Me"),
    ]

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    content = models.TextField(blank=True)
    privacy = models.CharField(max_length=20, choices=PRIVACY_CHOICES, default="public")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField("Tag", related_name="posts", blank=True)

    class Meta:
        ordering = ["-created_at"]  # newest posts first

    def __str__(self):
        return f"Post by {self.author} ({self.created_at.strftime('%Y-%m-%d')})"


class PostMedia(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="posts/media/")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.media_type} for Post {self.post.id}"


class Story(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stories")
    media = models.FileField(upload_to="stories/")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    def is_active(self):
        return self.expires_at > timezone.now()

    def __str__(self):
        return f"Story by {self.author} (expires {self.expires_at})"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)  # normalized (lowercase)
    display_name = models.CharField(max_length=50, blank=True)  # original case
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name
        self.name = self.name.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.display_name}"
