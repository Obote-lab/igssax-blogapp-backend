from rest_framework import permissions


class IsStreamerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow streamers to edit their streams.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the streamer
        return obj.streamer == request.user


class IsStreamParticipant(permissions.BasePermission):
    """
    Permission to only allow participants of a stream to perform actions.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        # For create operations, check if user is in the stream
        if request.method == "POST":
            stream_id = request.data.get("stream")
            if stream_id:
                from .models import StreamParticipant

                return StreamParticipant.objects.filter(
                    stream_id=stream_id, user=request.user, left_at__isnull=True
                ).exists()

        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        # Check if user is the owner of the object
        if hasattr(obj, "user") and obj.user == request.user:
            return True

        # Check if user is a participant in the stream
        if hasattr(obj, "stream"):
            from .models import StreamParticipant

            return StreamParticipant.objects.filter(
                stream=obj.stream, user=request.user, left_at__isnull=True
            ).exists()

        return False


class IsStreamerOrModerator(permissions.BasePermission):
    """
    Permission to only allow streamers or moderators to perform actions.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        # Streamer can always perform actions
        if hasattr(obj, "streamer") and obj.streamer == request.user:
            return True

        # Check if user is a moderator for stream-related objects
        stream = None
        if hasattr(obj, "stream"):
            stream = obj.stream
        elif hasattr(obj, "streamer"):  # For LiveStream objects
            stream = obj

        if stream:
            from .models import StreamParticipant

            return StreamParticipant.objects.filter(
                stream=stream, user=request.user, role="moderator", left_at__isnull=True
            ).exists()

        return False


class CanModerateStream(permissions.BasePermission):
    """
    Permission to check if user can moderate a stream (streamer or moderator).
    """

    def has_permission(self, request, view):
        # For actions that require stream_id in URL or data
        stream_id = view.kwargs.get("stream_id") or request.data.get("stream")
        if not stream_id:
            return False

        from .models import LiveStream, StreamParticipant

        try:
            stream = LiveStream.objects.get(id=stream_id)
        except LiveStream.DoesNotExist:
            return False

        # Streamer can always moderate
        if stream.streamer == request.user:
            return True

        # Check if user is a moderator
        return StreamParticipant.objects.filter(
            stream=stream, user=request.user, role="moderator", left_at__isnull=True
        ).exists()
