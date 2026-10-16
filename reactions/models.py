from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models
from django.db.models import Count, F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

User = get_user_model()

REACTION_TYPES = [
    ("like", "Like"),
    ("love", "Love"),
    ("haha", "Haha"),
    ("wow", "Wow"),
    ("sad", "Sad"),
    ("angry", "Angry"),
]


class Reaction(models.Model):
    """
    Generic Reaction model.
    Supports reacting to any content object (Post, Comment, etc.).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reactions")
    reaction_type = models.CharField(
        max_length=20, choices=REACTION_TYPES, default="like"
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "content_type", "object_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} reacted '{self.reaction_type}' on {self.content_object}"

    # --- CACHING / UTILS ---
    @staticmethod
    def build_cache_key(model_name: str, obj_id: int) -> str:
        """Return standardized cache key for reaction summaries."""
        return f"reaction_summary:{model_name}:{obj_id}"

    @staticmethod
    def compute_summary(
        content_type: ContentType, object_id: int, use_cache=True
    ) -> dict:
        """
        Compute the full reaction summary.
        Optionally caches results for 60 seconds.
        """
        key = Reaction.build_cache_key(content_type.model, object_id)
        if use_cache:
            cached = cache.get(key)
            if cached is not None:
                return cached

        summary = {
            r["reaction_type"]: r["count"]
            for r in Reaction.objects.filter(
                content_type=content_type, object_id=object_id
            )
            .values("reaction_type")
            .annotate(count=Count("id"))
        }

        if use_cache:
            cache.set(key, summary, timeout=60)
        return summary

    # --- CLASS METHODS ---
    @classmethod
    def add_or_update(cls, user, content_object, reaction_type: str):
        """
        Add a reaction or update it if it already exists.
        Returns (instance, created: bool)
        """
        content_type = ContentType.objects.get_for_model(content_object)
        instance, created = cls.objects.update_or_create(
            user=user,
            content_type=content_type,
            object_id=content_object.id,
            defaults={"reaction_type": reaction_type},
        )
        # Invalidate cache after change
        cache_key = cls.build_cache_key(content_type.model, content_object.id)
        cache.delete(cache_key)
        return instance, created

    @classmethod
    def remove(cls, user, content_object):
        """
        Remove a reaction by a user for a given object.
        """
        content_type = ContentType.objects.get_for_model(content_object)
        cls.objects.filter(
            user=user, content_type=content_type, object_id=content_object.id
        ).delete()
        # Invalidate cache
        cache_key = cls.build_cache_key(content_type.model, content_object.id)
        cache.delete(cache_key)


# --- SIGNALS FOR DENORMALIZED COUNTS ---
@receiver(post_save, sender=Reaction)
def increment_reactions_count(sender, instance, created, **kwargs):
    """
    Optional: increment denormalized reactions_count on the target object.
    Assumes target model has `reactions_count` field.
    """
    if not created:
        return
    obj = instance.content_object
    if hasattr(obj, "reactions_count"):
        obj.__class__.objects.filter(pk=obj.pk).update(
            reactions_count=F("reactions_count") + 1
        )


@receiver(post_delete, sender=Reaction)
def decrement_reactions_count(sender, instance, **kwargs):
    """
    Optional: decrement denormalized reactions_count on the target object.
    """
    obj = instance.content_object
    if hasattr(obj, "reactions_count"):
        obj.__class__.objects.filter(pk=obj.pk, reactions_count__gt=0).update(
            reactions_count=F("reactions_count") - 1
        )
