from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Follow, Profile, User, UserSettings

User = settings.AUTH_USER_MODEL

@receiver(post_save, sender=User)
def create_or_update_user_profile_and_settings(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        UserSettings.objects.get_or_create(user=instance)
    else:
        instance.profile.save()
        if hasattr(instance, "settings"):
            instance.settings.save()


@receiver(post_save, sender=Follow)
def update_follow_counts_on_create(sender, instance, created, **kwargs):
    if created:
        Profile.objects.filter(user=instance.follower).update(
            following_count=F("following_count") + 1
        )
        Profile.objects.filter(user=instance.following).update(
            followers_count=F("followers_count") + 1
        )


@receiver(post_delete, sender=Follow)
def update_follow_counts_on_delete(sender, instance, **kwargs):
    Profile.objects.filter(user=instance.follower).update(
        following_count=F("following_count") - 1
    )
    Profile.objects.filter(user=instance.following).update(
        followers_count=F("followers_count") - 1
    )

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_settings(sender, instance, created, **kwargs):
    if created:
        UserSettings.objects.create(user=instance)
    else:
        # make sure every user always has settings
        UserSettings.objects.get_or_create(user=instance)