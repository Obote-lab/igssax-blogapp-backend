from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from ..models import Reaction

# Default cache timeout: 10 minutes
CACHE_TIMEOUT = 60 * 10


def build_reaction_cache_key(model_class, obj_id):
    """Return a consistent cache key for a model's reaction summary."""
    model_name = model_class._meta.model_name
    return f"reaction_summary:{model_name}:{obj_id}"


def get_reaction_summary_cached(model_class, obj_id):
    """
    Retrieve cached reaction summary or compute and cache it.
    Works for any model that supports reactions (e.g. Post, Comment).
    """
    key = build_reaction_cache_key(model_class, obj_id)
    summary = cache.get(key)
    if summary:
        return summary

    # Compute fresh summary if not cached
    content_type = ContentType.objects.get_for_model(model_class)
    reaction_data = (
        Reaction.objects.filter(content_type=content_type, object_id=obj_id)
        .values("reaction_type")
        .annotate(count=Count("id"))
    )

    # Build a standardized dictionary for all possible reactions
    summary = {
        "like": 0,
        "love": 0,
        "haha": 0,
        "wow": 0,
        "sad": 0,
        "angry": 0,
    }

    for item in reaction_data:
        rtype = item["reaction_type"]
        if rtype in summary:
            summary[rtype] = item["count"]

    # Cache the computed summary
    cache.set(key, summary, CACHE_TIMEOUT)
    return summary


def invalidate_reaction_cache(model_class, obj_id):
    """
    Delete reaction summary cache for an object after a new reaction or removal.
    Called automatically from ReactionViewSet._after_reaction_change().
    """
    key = build_reaction_cache_key(model_class, obj_id)
    cache.delete(key)
