from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reactions")
    reaction_type = models.CharField(max_length=20, choices=REACTION_TYPES, default="like")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "content_type", "object_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} reacted '{self.reaction_type}' on {self.content_object}"

    @staticmethod
    def build_cache_key(model_name, obj_id):
        """Return standardized cache key for reaction summaries."""
        return f"reaction_summary:{model_name}:{obj_id}"

    @staticmethod
    def compute_summary(content_type, object_id):
        """Compute the full reaction summary dict directly from DB."""
        from django.db.models import Count
        reactions = Reaction.objects.filter(content_type=content_type, object_id=object_id)
        return {
            r["reaction_type"]: r["count"]
            for r in reactions.values("reaction_type").annotate(count=Count("id"))
        }
