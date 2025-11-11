from rest_framework import serializers
from django.contrib.auth import get_user_model
from ..models import DirectMessage
from reactions.utils.cache_utils import get_reaction_summary_for_instance

User = get_user_model()


class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]


class DirectMessageSerializer(serializers.ModelSerializer):
    sender = SimpleUserSerializer(read_only=True)
    recipient = SimpleUserSerializer(read_only=True)
    sender_id = serializers.IntegerField(write_only=True, required=False)
    recipient_id = serializers.IntegerField(write_only=True, required=True)
    attachment = serializers.FileField(required=False, allow_null=True)
    in_reply_to = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    read = serializers.BooleanField(read_only=True)
    delivered = serializers.BooleanField(read_only=True)

    class Meta:
        model = DirectMessage
        fields = [
            "id",
            "sender",
            "recipient",
            "sender_id",
            "recipient_id",
            "content",
            "attachment",
            "in_reply_to",
            "delivered",
            "read",
            "created_at",
            "conversation_key",
        ]
        read_only_fields = ["id", "sender", "delivered", "read", "created_at", "conversation_key"]

    def create(self, validated_data):
        """
        We accept recipient_id and optional in_reply_to id in the request.
        The view will set sender to request.user via perform_create.
        """
        request = self.context.get("request")
        sender = request.user

        recipient_id = validated_data.pop("recipient_id")
        in_reply_to_id = validated_data.pop("in_reply_to", None)

        # Resolve recipient
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"recipient_id": "Recipient not found"})

        # Resolve in_reply_to
        in_reply_to = None
        if in_reply_to_id:
            try:
                in_reply_to = DirectMessage.objects.get(id=in_reply_to_id)
            except DirectMessage.DoesNotExist:
                raise serializers.ValidationError({"in_reply_to": "Message to reply to not found"})

        dm = DirectMessage.objects.create(
            sender=sender,
            recipient=recipient,
            content=validated_data.get("content", ""),
            attachment=validated_data.get("attachment", None),
            in_reply_to=in_reply_to,
        )
        return dm
