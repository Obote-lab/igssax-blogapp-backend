from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from reactions.models import Reaction

from ..models import Comment, Conversation, ConversationMessage


class RecursiveCommentSerializer(serializers.ModelSerializer):
    """Recursive serializer for nested replies"""

    replies = serializers.SerializerMethodField()
    author = serializers.StringRelatedField(read_only=True)
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


class RecursiveField(serializers.Serializer):
    """Allow recursive nesting for replies"""

    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class LimitedRecursiveField(serializers.Serializer):
    """Recursive field with depth control"""

    def to_representation(self, value):
        parent_serializer = self.parent.parent
        depth = getattr(parent_serializer, "_depth", 0)

        if depth >= 4:  # 🚫 stop at level 4
            return []  # no more replies

        serializer_class = parent_serializer.__class__
        serializer = serializer_class(value, context=self.context)
        serializer._depth = depth + 1
        return serializer.data


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)
    replies = LimitedRecursiveField(many=True, read_only=True)

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
        ]


class ConversationMessageSerializer(serializers.ModelSerializer):
    sender = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ConversationMessage
        fields = ["id", "conversation", "sender", "content", "created_at"]
        read_only_fields = ["sender", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        return ConversationMessage.objects.create(sender=request.user, **validated_data)


class ConversationSerializer(serializers.ModelSerializer):
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
        conversation.participants.add(request.user)  # creator auto-joins
        return conversation
