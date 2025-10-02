from rest_framework import permissions, viewsets

from ..models import DirectMessage
from .serializers import DirectMessageSerializer


class DirectMessageViewSet(viewsets.ModelViewSet):
    queryset = DirectMessage.objects.all().select_related("sender", "recipient")
    serializer_class = DirectMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)
