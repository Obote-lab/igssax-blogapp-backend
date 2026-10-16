import mimetypes
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from comments.api.serializers import CommentSerializer
from reactions.models import Reaction
from reactions.utils.cache_utils import get_reaction_summary_cached
from users.api.serializers import UserSerializer
from ..models import (
    Post, PostMedia, PostShare, PostView, Story, Tag, 
    StoryComment, StoryReaction, StoryView, PostTag, 
    PostInsight, ContentModeration, PostVisibility
)
from users.models import User
from drf_spectacular.utils import extend_schema_field


# ========== MEDIA SERIALIZERS ==========

class PostMediaSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    
    class Meta:
        model = PostMedia
        fields = ["id", "media_type", "file", "thumbnail", "uploaded_at"]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_file(self, obj) -> str:
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if obj.file else None

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumbnail(self, obj) -> str:
        request = self.context.get("request")
        # In production, generate thumbnails using django-imagekit or similar
        return request.build_absolute_uri(obj.file.url) if obj.file else None


# ========== TAG SERIALIZERS ==========

class TagSerializer(serializers.ModelSerializer):
    post_count = serializers.IntegerField(source='posts.count', read_only=True)
    
    class Meta:
        model = Tag
        fields = ["id", "name", "display_name", "post_count", "created_at"]


class PostTagSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = PostTag
        fields = ["id", "user", "user_name", "user_avatar", "position_x", "position_y", "tagged_at"]
    
    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_user_avatar(self, obj) -> str|None:
        request = self.context.get('request')
        if hasattr(obj.user, 'profile') and obj.user.profile.avatar:
            return request.build_absolute_uri(obj.user.profile.avatar.url)
        return None


# ========== POST SERIALIZERS ==========

class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tagged_users = PostTagSerializer(source='posttag_set', many=True, read_only=True)
    reactions = serializers.SerializerMethodField()
    media_count = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True, source="comment_total")
    share_count = serializers.IntegerField(read_only=True, source="share_total")
    is_edited = serializers.SerializerMethodField()
    link_preview = serializers.SerializerMethodField()
    location_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            "id", "author", "content", "privacy", "post_type",
            "created_at", "updated_at", "media", "media_count",
            "tags", "tagged_users", "comment_count", "reactions",
            "share_count", "views_count", "is_edited", "link_preview",
            "location_info", "link_url", "link_title", "link_description",
            "link_image", "location", "latitude", "longitude",
            "is_scheduled", "scheduled_for", "is_draft"
        ]
        read_only_fields = ['is_edited', 'link_preview', 'location_info']

    @extend_schema_field(serializers.IntegerField())
    def get_comment_count(self, obj) -> int:
        return obj.comments.count()

    @extend_schema_field(serializers.IntegerField())
    def get_media_count(self, obj) -> int:
        return obj.media.count()

    @extend_schema_field(serializers.BooleanField())
    def get_is_edited(self, obj) -> bool:
        return obj.edited_count > 0

    @extend_schema_field(serializers.DictField())
    def get_link_preview(self, obj) -> dict:
        if obj.post_type == 'link' and obj.link_url:
            return {
                'url': obj.link_url,
                'title': obj.link_title,
                'description': obj.link_description,
                'image': obj.link_image
            }
        return {}

    @extend_schema_field(serializers.DictField())
    def get_location_info(self, obj) -> dict:
        if obj.location:
            return {
                'name': obj.location,
                'coordinates': {
                    'latitude': float(obj.latitude) if obj.latitude else None,
                    'longitude': float(obj.longitude) if obj.longitude else None
                } if obj.latitude and obj.longitude else None
            }
        return {}

    @extend_schema_field(serializers.DictField())
    def get_reactions(self, obj) -> dict:
        if hasattr(obj, "likes"):
            return {
                "like": getattr(obj, "likes", 0),
                "love": getattr(obj, "loves", 0),
                "wow": getattr(obj, "wows", 0),
                "sad": getattr(obj, "sads", 0),
                "angry": getattr(obj, "angrys", 0),
            }
        summary = get_reaction_summary_cached(Post, obj.id)
        request = self.context.get("request")
        user_reacted = None
        if request and request.user.is_authenticated:
            ctype = ContentType.objects.get_for_model(obj)
            user_reaction = Reaction.objects.filter(
                content_type=ctype,
                object_id=obj.id,
                user=request.user,
            ).first()
            if user_reaction:
                user_reacted = user_reaction.reaction_type

        total = sum(summary.values())

        return {
            "summary": summary,
            "total": total,
            "user_reacted": user_reacted,
        }


class PostCreateSerializer(serializers.ModelSerializer):
    author = serializers.HiddenField(default=serializers.CurrentUserDefault())
    media_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
    )
    tag_names = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
    )
    tagged_user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )
    tagged_positions = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of {'user_id': int, 'x': float, 'y': float}"
    )
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    save_as_draft = serializers.BooleanField(write_only=True, required=False, default=False)
    
    class Meta:
        model = Post
        fields = [
            "author", "content", "privacy", "post_type", "media_files", 
            "tag_names", "tagged_user_ids", "tagged_positions", "link_url",
            "link_title", "link_description", "link_image", "location",
            "latitude", "longitude", "scheduled_for", "save_as_draft"
        ]
        read_only_fields = ["author"]

    def validate(self, data):
        # Validate post type constraints
        if data.get('post_type') == 'link' and not data.get('link_url'):
            raise serializers.ValidationError(
                {"link_url": "Link URL is required for link posts."}
            )
        
        # Validate scheduling
        scheduled_for = data.get('scheduled_for')
        if scheduled_for and scheduled_for <= timezone.now():
            raise serializers.ValidationError(
                {"scheduled_for": "Scheduled time must be in the future."}
            )
        
        return data

    def create(self, validated_data):
        media_files = validated_data.pop("media_files", [])
        tag_names = validated_data.pop("tag_names", [])
        tagged_user_ids = validated_data.pop("tagged_user_ids", [])
        tagged_positions = validated_data.pop("tagged_positions", [])
        save_as_draft = validated_data.pop("save_as_draft", False)
        
        with transaction.atomic():
            # Handle draft/scheduled status
            if save_as_draft:
                validated_data['is_draft'] = True
                validated_data['saved_at'] = timezone.now()
            elif validated_data.get('scheduled_for'):
                validated_data['is_scheduled'] = True
            
            post = Post.objects.create(**validated_data)

            # Handle media
            for file in media_files:
                content_type, _ = mimetypes.guess_type(file.name)
                media_type = (
                    "video" if content_type and "video" in content_type else "image"
                )
                PostMedia.objects.create(post=post, file=file, media_type=media_type)

            # Handle tags
            for name in tag_names:
                clean_name = name.strip().lower()
                tag, _ = Tag.objects.get_or_create(name=clean_name)
                if not tag.display_name:
                    tag.display_name = name.strip()
                    tag.save()
                post.tags.add(tag)

            # Handle user tagging
            for user_id in tagged_user_ids:
                try:
                    user = User.objects.get(id=user_id)
                    PostTag.objects.create(post=post, user=user)
                except User.DoesNotExist:
                    pass
            
            # Handle tagged positions (for photo tagging)
            for tag_data in tagged_positions:
                user_id = tag_data.get('user_id')
                position_x = tag_data.get('x')
                position_y = tag_data.get('y')
                try:
                    user = User.objects.get(id=user_id)
                    PostTag.objects.create(
                        post=post, 
                        user=user, 
                        position_x=position_x,
                        position_y=position_y
                    )
                except User.DoesNotExist:
                    pass

        return post

    def to_representation(self, instance):
        return PostSerializer(instance, context=self.context).data

class PostUpdateSerializer(PostCreateSerializer):
    """Serializer for updating posts with edit tracking"""
    
    def update(self, instance, validated_data):
        # Preserve original data for edit history
        original_content = instance.content
        # Update the instance
        instance = super().update(instance, validated_data)
        # Edit history is handled by the pre_save signal
        return instance


# ========== STORY SERIALIZERS ==========

class StorySerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)
    author_details = UserSerializer(source='author', read_only=True)
    is_active = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    poll_results = serializers.SerializerMethodField()
    user_has_reacted = serializers.SerializerMethodField()
    user_has_voted = serializers.SerializerMethodField()
    
    class Meta:
        model = Story
        fields = [
            "id", "author", "author_details", "story_type", "media",
            "created_at", "expires_at", "is_active", "text_content",
            "background_color", "poll_question", "poll_option_a",
            "poll_option_b", "poll_results", "reactions_count",
            "comments_count", "views_count", "reply_count",
            "user_has_reacted", "user_has_voted"
        ]
    
    @extend_schema_field(serializers.BooleanField())
    def get_is_active(self, obj) -> bool:
        return obj.is_active()

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_media(self, obj) -> str:
        request = self.context.get("request")
        if obj.media:
            return request.build_absolute_uri(obj.media.url)
        return None

    @extend_schema_field(serializers.DictField())
    def get_poll_results(self, obj) -> dict:
        if obj.story_type == 'poll':
            total = obj.poll_votes_a + obj.poll_votes_b
            return {
                'option_a': {
                    'text': obj.poll_option_a,
                    'votes': obj.poll_votes_a,
                    'percentage': (obj.poll_votes_a / total * 100) if total > 0 else 0
                },
                'option_b': {
                    'text': obj.poll_option_b,
                    'votes': obj.poll_votes_b,
                    'percentage': (obj.poll_votes_b / total * 100) if total > 0 else 0
                },
                'total_votes': total
            }
        return {}

    @extend_schema_field(serializers.BooleanField())
    def get_user_has_reacted(self, obj) -> bool:
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return StoryReaction.objects.filter(
                story=obj, user=request.user
            ).exists()
        return False

    @extend_schema_field(serializers.BooleanField())
    def get_user_has_voted(self, obj) -> bool:
        # In production, you'd track individual votes
        # This is a simplified version
        request = self.context.get('request')
        if request and request.user.is_authenticated and obj.story_type == 'poll':
            # Check if user has voted (you'd need a StoryVote model)
            return False
        return False


class StoryCreateSerializer(serializers.ModelSerializer):
    story_type = serializers.ChoiceField(choices=Story.STORY_TYPES, default='image')
    background_color = serializers.CharField(required=False, allow_blank=True)
    text_content = serializers.CharField(required=False, allow_blank=True)
    poll_question = serializers.CharField(required=False, allow_blank=True)
    poll_option_a = serializers.CharField(required=False, allow_blank=True)
    poll_option_b = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = Story
        fields = [
            "id", "media", "story_type", "background_color", 
            "text_content", "poll_question", "poll_option_a", "poll_option_b"
        ]
    
    def validate(self, data):
        story_type = data.get('story_type', 'image')
        
        if story_type == 'text' and not data.get('text_content'):
            raise serializers.ValidationError(
                {"text_content": "Text content is required for text stories."}
            )
        
        if story_type == 'poll':
            if not data.get('poll_question'):
                raise serializers.ValidationError(
                    {"poll_question": "Poll question is required for poll stories."}
                )
            if not data.get('poll_option_a') or not data.get('poll_option_b'):
                raise serializers.ValidationError(
                    {"poll_options": "Both poll options are required for poll stories."}
                )
        
        if story_type in ['image', 'video'] and not data.get('media'):
            raise serializers.ValidationError(
                {"media": "Media file is required for image/video stories."}
            )
        
        return data


# ========== OTHER SERIALIZERS ==========

class StoryFeedUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "name", "avatar"]

    def get_name(self, obj):
        return obj.first_name or obj.email

    def get_avatar(self, obj):
        if hasattr(obj, "profile") and obj.profile.avatar:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.profile.avatar.url)
        return None


class StoryItemSerializer(serializers.ModelSerializer):
    media = serializers.SerializerMethodField()
    story_type = serializers.CharField(read_only=True)

    class Meta:
        model = Story
        fields = ["id", "media", "story_type", "created_at", "expires_at"]

    def get_media(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.media.url) if obj.media else None


class PostShareSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    post_preview = PostSerializer(source='post', read_only=True)

    class Meta:
        model = PostShare
        fields = ["id", "post", "post_preview", "user", "share_type", "shared_at"]
        read_only_fields = ["id", "user", "shared_at"]


class StoryReactionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = StoryReaction
        fields = ['id', 'user', 'user_avatar', 'story', 'reaction_type', 'created_at']
        read_only_fields = ['user', 'created_at']
    
    @extend_schema_field(serializers.URLField(allow_null=True)) 
    def get_user_avatar(self, obj) ->str|None:
        request = self.context.get('request')
        if hasattr(obj.user, 'profile') and obj.user.profile.avatar:
            return request.build_absolute_uri(obj.user.profile.avatar.url)
        return None


class StoryCommentSerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)
    author_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = StoryComment
        fields = ['id', 'story', 'author', 'author_avatar', 'content', 'created_at', 'updated_at']
        read_only_fields = ['author', 'created_at', 'updated_at']
    

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_author_avatar(self, obj) ->str|None:
        request = self.context.get('request')
        if hasattr(obj.author, 'profile') and obj.author.profile.avatar:
            return request.build_absolute_uri(obj.author.profile.avatar.url)
        return None


class CreateStoryReactionSerializer(serializers.Serializer):
    reaction_type = serializers.ChoiceField(choices=StoryReaction.REACTION_TYPES)


class CreateStoryCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryComment
        fields = ['content']


class ContentModerationSerializer(serializers.ModelSerializer):
    reported_by = UserSerializer(read_only=True)
    post_preview = PostSerializer(source='post', read_only=True)
    
    class Meta:
        model = ContentModeration
        fields = [
            'id', 'post', 'post_preview', 'reported_by', 'reason',
            'status', 'reviewed_by', 'reviewed_at'
        ]
        read_only_fields = ['reported_by', 'reviewed_by', 'reviewed_at']


class PostInsightSerializer(serializers.ModelSerializer):
    post = PostSerializer(read_only=True)
    engagement_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = PostInsight
        fields = [
            'id', 'post', 'reach', 'engagement', 'clicks', 'shares',
            'male_viewers', 'female_viewers', 'age_18_24', 'age_25_34',
            'engagement_rate', 'created_at', 'updated_at'
        ]
    
    @extend_schema_field(serializers.FloatField()) 
    def get_engagement_rate(self, obj) ->float:
        if obj.reach > 0:
            return (obj.engagement / obj.reach) * 100
        return 0


# ========== BULK OPERATION SERIALIZERS ==========

class BulkTagSerializer(serializers.Serializer):
    """Serializer for bulk tagging operations"""
    post_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of post IDs to tag"
    )
    tag_names = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of tag names to add"
    )


class BulkDeleteSerializer(serializers.Serializer):
    """Serializer for bulk delete operations"""
    post_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of post IDs to delete"
    )
    permanent = serializers.BooleanField(
        default=False,
        help_text="Permanently delete (if false, marks as deleted)"
    )