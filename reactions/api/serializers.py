from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from comments.models import Comment
from posts.models import Post
from ..models import Reaction


class ReactionSerializer(serializers.ModelSerializer):
    post = serializers.IntegerField(required=False, write_only=True)
    comment = serializers.IntegerField(required=False, write_only=True)
    username = serializers.SerializerMethodField()

    class Meta:
        model = Reaction
        fields = [
            "id",
            "reaction_type",
            "user",
            "username",
            "post",
            "comment",
            "object_id",
            "content_type",
            "created_at",
        ]
        read_only_fields = ["user", "object_id", "content_type", "created_at"]

    def get_username(self, obj):
        return obj.user.username

    def validate(self, attrs):
        post_id = attrs.pop("post", None)
        comment_id = attrs.pop("comment", None)

        if post_id:
            attrs["content_type"] = ContentType.objects.get_for_model(Post)
            attrs["object_id"] = post_id
        elif comment_id:
            attrs["content_type"] = ContentType.objects.get_for_model(Comment)
            attrs["object_id"] = comment_id
        else:
            view = self.context.get("view")
            if not (view and getattr(view, "action", None) == "toggle"):
                raise serializers.ValidationError(
                    "You must provide either a post or a comment."
                )
        return attrs

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.content_type.model == "post":
            rep["post"] = instance.object_id
        elif instance.content_type.model == "comment":
            rep["comment"] = instance.object_id
        return rep
