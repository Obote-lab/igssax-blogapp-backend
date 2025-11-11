from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from reactions.models import Reaction
from ..models import Comment, Conversation, ConversationMessage, CommentAttachment
from django.contrib.auth import get_user_model
from users.models import Profile,User  
from reactions.utils.cache_utils import get_reaction_summary_cached




User = get_user_model()


# --- MINI PROFILE SERIALIZER ---
class ProfileMiniSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["avatar", "avatar_url"]

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj.avatar and hasattr(obj.avatar, "url"):
            return request.build_absolute_uri(obj.avatar.url)
        return None


# --- MINI USER SERIALIZER ---
class UserProfileMiniSerializer(serializers.ModelSerializer):
    profile = ProfileMiniSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "profile"]


# --- COMMENT SERIALIZERS ---
class RecursiveCommentSerializer(serializers.ModelSerializer):
    """Recursive serializer for nested replies."""

    replies = serializers.SerializerMethodField()
    author = UserProfileMiniSerializer(read_only=True)
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "author",
            "content",
            "created_at",
            "updated_at",
            "parent",
            "replies",
            "reactions",
        ]

    def get_replies(self, obj):
        if obj.replies.exists():
            return RecursiveCommentSerializer(
                obj.replies.all(), many=True, context=self.context
            ).data
        return []

    def get_reactions(self, obj):
        ctype = ContentType.objects.get_for_model(obj)
        reactions = Reaction.objects.filter(content_type=ctype, object_id=obj.id)
        summary = {}
        for r in reactions:
            summary[r.reaction_type] = summary.get(r.reaction_type, 0) + 1
        return summary


class LimitedRecursiveField(serializers.Serializer):
    """Recursive field that stops serialization beyond 4 nested reply levels."""

    def to_representation(self, value):
        parent_serializer = self.parent.parent
        depth = getattr(parent_serializer, "_depth", 0)
        if depth >= 4:
            return []
        serializer_class = parent_serializer.__class__
        serializer = serializer_class(value, context=self.context)
        serializer._depth = depth + 1
        return serializer.data


class CommentAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = CommentAttachment
        fields = ["id", "file", "file_url", "gif_url", "uploaded_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and hasattr(obj.file, "url"):
            return request.build_absolute_uri(obj.file.url)
        return None


class CommentSerializer(serializers.ModelSerializer):
    author = UserProfileMiniSerializer(read_only=True)
    author_name = serializers.CharField(source="author.username", read_only=True)
    author_avatar = serializers.SerializerMethodField()
    # Use LimitedRecursiveField instead of manual get_replies
    replies = LimitedRecursiveField(many=True, read_only=True)
    reaction_summary = serializers.SerializerMethodField()
    attachments = CommentAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "parent",
            "author",
            "author_name",
            "author_avatar",
            "content",
            "attachments",
            "created_at",
            "updated_at",
            "replies",
            "reaction_summary",
        ]
        read_only_fields = ["author", "created_at", "updated_at"]

    def get_author_avatar(self, obj):
        try:
            if obj.author.profile.avatar:
                request = self.context.get("request")
                return request.build_absolute_uri(obj.author.profile.avatar.url)
        except Exception:
            pass
        return None

    def get_reaction_summary(self, obj):
        if hasattr(obj, "likes"):
            return {
                "like": getattr(obj, "likes", 0),
                "love": getattr(obj, "loves", 0),
                "wow": getattr(obj, "wows", 0),
                "sad": getattr(obj, "sads", 0),
                "angry": getattr(obj, "angrys", 0),
            }
        from reactions.utils.cache_utils import get_reaction_summary_cached
        return get_reaction_summary_cached(Comment, obj.id)

    def create(self, validated_data):
        request = self.context.get("request")

        content = request.data.get("content", "").strip()
        files = request.FILES.getlist("attachments")

        # Handle GIF URLs
        gif_urls = []
        gif_urls_data = request.data.get("gif_urls", [])
        if isinstance(gif_urls_data, str):
            gif_urls = [gif_urls_data] if gif_urls_data.strip() else []
        elif isinstance(gif_urls_data, list):
            gif_urls = [url for url in gif_urls_data if url and url.strip()]

        if not content and not files and not gif_urls:
            raise serializers.ValidationError(
                {"content": ["Comment must have text, attachments, or GIFs."]}
            )

        # Ensure post is set
        if "post" not in validated_data:
            post_id = request.data.get("post")
            if post_id:
                from posts.models import Post
                try:
                    validated_data["post"] = Post.objects.get(id=post_id)
                except Post.DoesNotExist:
                    raise serializers.ValidationError({"post": ["Post not found."]})

        # Handle parent explicitly
        parent_id = request.data.get("parent")
        if parent_id:
            try:
                validated_data["parent"] = Comment.objects.get(id=parent_id)
            except Comment.DoesNotExist:
                raise serializers.ValidationError({"parent": ["Parent comment not found."]})

        # Set author and content
        validated_data["author"] = request.user
        validated_data["content"] = content

        # Create comment
        comment = Comment.objects.create(**validated_data)

        # Attachments
        for file in files:
            CommentAttachment.objects.create(comment=comment, file=file)
        for gif_url in gif_urls:
            CommentAttachment.objects.create(comment=comment, gif_url=gif_url.strip())

        return comment

    def validate_content(self, value):
        """
        Allow empty content if there are attachments
        """
        return value or ""

 
# --- CONVERSATION SERIALIZERS ---
class ConversationMessageSerializer(serializers.ModelSerializer):
    """Serialize individual messages inside a conversation."""
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    delivered_to = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()

    class Meta:
        model = ConversationMessage
        fields = [
            "id",
            "conversation",
            "sender",
            "sender_username",
            "content",
            "created_at",
            "delivered_to",
            "read_by",
        ]

    def get_delivered_to(self, obj):
        return [user.username for user in obj.delivered_to.all()]

    def get_read_by(self, obj):
        return [user.username for user in obj.read_by.all()]


class ConversationSerializer(serializers.ModelSerializer):
    """Serialize an entire conversation including its messages."""
    participants = serializers.StringRelatedField(many=True, read_only=True)
    messages = ConversationMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "name", "created_by", "participants", "created_at", "messages"]
        read_only_fields = ["created_by", "created_at", "messages"]

    def create(self, validated_data):
        request = self.context.get("request")
        conversation = Conversation.objects.create(
            created_by=request.user, **validated_data
        )
        conversation.participants.add(request.user)
        return conversation
