from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Follow, Friendship, Profile, UserSettings

User = get_user_model()


# USER CREATION
@receiver(post_save, sender=User)
def create_user_profile_and_settings(sender, instance, created, **kwargs):
    """
    Ensure every User has exactly one Profile and UserSettings.
    Safe against race conditions and duplicate signal firing.
    """
    if not created:
        return
    # Use get_or_create for absolute safety
    Profile.objects.get_or_create(user=instance)
    UserSettings.objects.get_or_create(user=instance)


# FOLLOW COUNTERS
@receiver(post_save, sender=Follow)
def update_follow_counts_on_create(sender, instance, created, **kwargs):
    """
    Increment follower / following counts atomically
    ONLY when a Follow is first created.
    """
    if not created:
        return

    with transaction.atomic():
        Profile.objects.filter(user=instance.follower).update(
            following_count=F("following_count") + 1
        )
        Profile.objects.filter(user=instance.following).update(
            followers_count=F("followers_count") + 1
        )


@receiver(post_delete, sender=Follow)
def update_follow_counts_on_delete(sender, instance, **kwargs):
    """
    Decrement follower / following counts atomically.
    Counts are clamped at 0 to prevent corruption.
    """
    with transaction.atomic():
        Profile.objects.filter(user=instance.follower).update(
            following_count=Greatest(F("following_count") - 1, 0)
        )
        Profile.objects.filter(user=instance.following).update(
            followers_count=Greatest(F("followers_count") - 1, 0)
        )


# FRIENDSHIP STATUS TRACKING (CRITICAL)
@receiver(pre_save, sender=Friendship)
def friendship_pre_save(sender, instance, **kwargs):
    """
    Capture previous friendship status BEFORE save.
    This enables correct detection of status transitions.
    """
    if not instance.pk:
        instance._previous_status = None
        return

    instance._previous_status = (
        Friendship.objects.filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


@receiver(post_save, sender=Friendship)
def update_friend_counts_on_status_change(sender, instance, created, **kwargs):
    """
    Increment friends_count ONLY when friendship transitions
    from NON-ACCEPTED → ACCEPTED.
    """
    if created:
        # New friendships are always PENDING
        return

    if (
        instance._previous_status != Friendship.Status.ACCEPTED
        and instance.status == Friendship.Status.ACCEPTED
    ):
        with transaction.atomic():
            Profile.objects.filter(user=instance.requester).update(
                friends_count=F("friends_count") + 1
            )
            Profile.objects.filter(user=instance.receiver).update(
                friends_count=F("friends_count") + 1
            )


@receiver(post_delete, sender=Friendship)
def update_friend_counts_on_delete(sender, instance, **kwargs):
    """
    Decrement friends_count ONLY if the deleted friendship
    was ACCEPTED.
    """
    if instance.status != Friendship.Status.ACCEPTED:
        return

    with transaction.atomic():
        Profile.objects.filter(user=instance.requester).update(
            friends_count=Greatest(F("friends_count") - 1, 0)
        )
        Profile.objects.filter(user=instance.receiver).update(
            friends_count=Greatest(F("friends_count") - 1, 0)
        )
