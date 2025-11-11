import re

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import Truncator

from comments.models import Comment
from messaging.models import DirectMessage 

from .models import Notification, NotificationPreference
from .utils import create_notification

User = get_user_model()


# 1. Automatically create Notification Preferences when a user is created
@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    if created:
        NotificationPreference.objects.create(user=instance)


# 2. Comment Notifications (new comment or reply)
@receiver(post_save, sender=Comment)
def comment_notifications(sender, instance, created, **kwargs):
    if not created:
        return

    comment = instance
    author = comment.author
    post_author = getattr(comment.post, "author", None)

    # Notify post author if someone comments on their post
    if post_author and post_author != author:
        create_notification(
            recipient=post_author,
            sender=author,
            notification_type=Notification.NotificationType.POST_COMMENT,
            title="New Comment on Your Post",
            message=f"{author.get_full_name()} commented: {Truncator(comment.content).chars(80)}",
            instance=comment,
        )

    # Notify parent comment author if this is a reply
    if comment.parent and comment.parent.author != author:
        create_notification(
            recipient=comment.parent.author,
            sender=author,
            notification_type=Notification.NotificationType.COMMENT_REPLY,
            title="New Reply to Your Comment",
            message=f"{author.get_full_name()} replied: {Truncator(comment.content).chars(80)}",
            instance=comment,
        )

    # Detect mentions (e.g., "@username")
    detect_mentions_and_notify(comment.content, author, comment)


# 3. Direct Message Notifications
@receiver(post_save, sender=DirectMessage)
def direct_message_notification(sender, instance, created, **kwargs):
    """
    Notify recipient when they receive a new direct message.
    """
    if not created:
        return

    message = instance
    sender_user = message.sender
    recipient = message.recipient

    create_notification(
        recipient=recipient,
        sender=sender_user,
        notification_type=Notification.NotificationType.MESSAGE,
        title=f"New Message from {sender_user.get_full_name()}",
        message=Truncator(message.content).chars(100),
        instance=message,
    )


# 4. Mention Detection Utility
def detect_mentions_and_notify(text, sender, instance):
    """
    Detect @username mentions and notify mentioned users.
    """
    usernames = re.findall(r"@(\w+)", text)
    for username in usernames:
        try:
            recipient = User.objects.get(username=username)
            if recipient != sender:
                create_notification(
                    recipient=recipient,
                    sender=sender,
                    notification_type=Notification.NotificationType.COMMENT_MENTION,
                    title="You Were Mentioned in a Comment",
                    message=f"{sender.get_full_name()} mentioned you: {Truncator(text).chars(100)}",
                    instance=instance,
                )
        except User.DoesNotExist:
            continue


#5. Welcome Notification for New Users
@receiver(post_save, sender=User)
def send_welcome_notification(sender, instance, created, **kwargs):
    if created:
        create_notification(
            recipient=instance,
            title="Welcome to the platform!",
            message=f"Hello {instance.username}, your account has been created successfully.",
            notification_type="user_welcome",
        )
