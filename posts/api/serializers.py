import mimetypes

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework import serializers

from comments.api.serializers import RecursiveCommentSerializer
from reactions.models import Reaction
from users.api.serializers import UserSerializer

from ..models import Post, PostMedia, Story, Tag


class PostMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostMedia
        fields = ["id", "media_type", "file", "uploaded_at"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "display_name", "created_at"]


class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    comments = RecursiveCommentSerializer(many=True, read_only=True)
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "author",
            "content",
            "privacy",
            "created_at",
            "updated_at",
            "media",
            "tags",
            "comments",
            "reactions",
        ]

    def get_reactions(self, obj):
        ctype = ContentType.objects.get_for_model(obj)
        reactions = Reaction.objects.filter(content_type=ctype, object_id=obj.id)
        summary = {}
        for r in reactions:
            summary[r.reaction_type] = summary.get(r.reaction_type, 0) + 1
        return summary


class PostCreateSerializer(serializers.ModelSerializer):
    author = serializers.HiddenField(default=serializers.CurrentUserDefault())

    media_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        help_text="List of media files (images/videos) to attach to the post.",
    )
    tag_names = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        help_text="List of tag names to associate with the post.",
    )

    class Meta:
        model = Post
        fields = ["author", "content", "privacy", "media_files", "tag_names"]
        read_only_fields = ["author"]

    def create(self, validated_data):
        media_files = validated_data.pop("media_files", [])
        tag_names = validated_data.pop("tag_names", [])

        with transaction.atomic():
            # ✅ Create post (author comes from CurrentUserDefault)
            post = Post.objects.create(**validated_data)

            # ✅ Save media with mimetype detection
            for file in media_files:
                try:
                    content_type, _ = mimetypes.guess_type(file.name)
                except Exception:
                    content_type = None

                media_type = (
                    "video" if content_type and "video" in content_type else "image"
                )
                PostMedia.objects.create(post=post, file=file, media_type=media_type)

            # ✅ Save tags
            for name in tag_names:
                clean_name = name.strip()
                tag, _ = Tag.objects.get_or_create(name=clean_name.lower())
                if not tag.display_name:
                    tag.display_name = clean_name
                    tag.save()
                post.tags.add(tag)

        return post

    def to_representation(self, instance):
        """
        Return the full PostSerializer representation after creation,
        so the frontend immediately receives the complete post object.
        """
        from .serializers import PostSerializer  # avoid circular import

        return PostSerializer(instance, context=self.context).data


class StorySerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = ["id", "author", "media", "created_at", "expires_at", "is_active"]

    def get_is_active(self, obj) -> bool:
        return obj.is_active()
