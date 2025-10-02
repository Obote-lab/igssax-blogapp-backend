from rest_framework import serializers

from ..models import DirectMessage


class DirectMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DirectMessage
        fields = ["id", "sender", "recipient", "content", "post_url", "created_at"]
        read_only_fields = ["sender", "created_at"]
