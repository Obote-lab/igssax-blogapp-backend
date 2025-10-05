from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

User = settings.AUTH_USER_MODEL


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        FRIEND_REQUEST = "friend_request", _("Friend Request")
        FRIEND_ACCEPTED = "friend_accepted", _("Friend Request Accepted")
        POST_LIKE = "post_like", _("Post Like")
        POST_COMMENT = "post_comment", _("Post Comment")
        COMMENT_REPLY = "comment_reply", _("Comment Reply")
        MESSAGE = "message", _("New Message")
        POST_MENTION = "post_mention", _("Post Mention")
        COMMENT_MENTION = "comment_mention", _("Comment Mention")
        SYSTEM = "system", _("System Notification")

    recipient = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="notifications"
    )
    sender = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name="sent_notifications"
    )
    notification_type = models.CharField(
        max_length=50, 
        choices=NotificationType.choices
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Generic foreign key to any related object
    content_type = models.ForeignKey(
        'contenttypes.ContentType', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
        ]

    def __str__(self):
        return f"{self.notification_type} for {self.recipient.email}"

    def mark_as_read(self):
        self.is_read = True
        self.save()


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name="notification_preferences"
    )
    
    # Email notifications
    email_friend_requests = models.BooleanField(default=True)
    email_friend_acceptances = models.BooleanField(default=True)
    email_post_likes = models.BooleanField(default=True)
    email_post_comments = models.BooleanField(default=True)
    email_comment_replies = models.BooleanField(default=True)
    email_mentions = models.BooleanField(default=True)
    email_messages = models.BooleanField(default=False)
    email_system = models.BooleanField(default=True)
    
    # Push notifications
    push_friend_requests = models.BooleanField(default=True)
    push_friend_acceptances = models.BooleanField(default=True)
    push_post_likes = models.BooleanField(default=True)
    push_post_comments = models.BooleanField(default=True)
    push_comment_replies = models.BooleanField(default=True)
    push_mentions = models.BooleanField(default=True)
    push_messages = models.BooleanField(default=True)
    push_system = models.BooleanField(default=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification preferences for {self.user.email}"