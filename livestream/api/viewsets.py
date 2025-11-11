from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import (LiveStream, StreamAnalytics, StreamBan, StreamMessage,
                      StreamParticipant, StreamReaction)
from ..permissions import IsStreamerOrReadOnly, IsStreamParticipant
from .serializers import (LiveStreamCreateSerializer, LiveStreamSerializer,
                          LiveStreamUpdateSerializer,
                          StreamAnalyticsSerializer, StreamBanSerializer,
                          StreamMessageSerializer, StreamParticipantSerializer,
                          StreamReactionSerializer, StreamRecording,
                          StreamRecordingSerializer)


class LiveStreamViewSet(viewsets.ModelViewSet):
    queryset = LiveStream.objects.all().select_related("streamer")
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsStreamerOrReadOnly]

    def get_serializer_class(self):
        if self.action == "create":
            return LiveStreamCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return LiveStreamUpdateSerializer
        return LiveStreamSerializer

    def get_queryset(self):
        queryset = self.queryset
        user = self.request.user

        # Filter based on privacy and user permissions
        if user.is_authenticated:
            # Show public streams + user's own streams
            # Note: You'll need to implement friend logic separately
            queryset = queryset.filter(
                Q(privacy="public")
                | Q(streamer=user)
                | Q(privacy="friends")  # Placeholder - add friend logic when ready
            ).distinct()
        else:
            # Show only public streams for anonymous users
            queryset = queryset.filter(privacy="public")

        # Additional filters
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        category_filter = self.request.query_params.get("category")
        if category_filter:
            queryset = queryset.filter(category__icontains=category_filter)

        streamer_filter = self.request.query_params.get("streamer")
        if streamer_filter:
            queryset = queryset.filter(streamer_id=streamer_filter)

        # Search functionality
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(category__icontains=search)
            )

        return queryset

    def perform_create(self, serializer):
        serializer.save(streamer=self.request.user)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def start_stream(self, request, pk=None):
        stream = self.get_object()

        if stream.streamer != request.user:
            return Response(
                {"error": "Only the streamer can start the stream"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if stream.status == LiveStream.StreamStatus.LIVE:
            return Response(
                {"error": "Stream is already live"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Use the model method instead of direct assignment
        stream.start_stream()

        # Create analytics record if it doesn't exist
        StreamAnalytics.objects.get_or_create(stream=stream)

        # Add streamer as participant with moderator role
        StreamParticipant.objects.get_or_create(
            stream=stream,
            user=request.user,
            defaults={
                "role": StreamParticipant.ParticipantRole.MODERATOR,
                "joined_at": timezone.now(),
            },
        )

        return Response({"message": "Stream started successfully"})

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def end_stream(self, request, pk=None):
        stream = self.get_object()

        if stream.streamer != request.user:
            return Response(
                {"error": "Only the streamer can end the stream"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if stream.status != LiveStream.StreamStatus.LIVE:
            return Response(
                {"error": "Stream is not live"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Use the model method
        stream.end_stream()

        # Update all participants to mark as left
        StreamParticipant.objects.filter(stream=stream, left_at__isnull=True).update(
            left_at=timezone.now()
        )

        return Response({"message": "Stream ended successfully"})

    @action(detail=False, methods=["get"])
    def live_now(self, request):
        """Get all currently live streams"""
        live_streams = self.get_queryset().filter(status=LiveStream.StreamStatus.LIVE)
        page = self.paginate_queryset(live_streams)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(live_streams, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def participants(self, request, pk=None):
        """Get all participants for a stream"""
        stream = self.get_object()

        if not stream.can_view(request.user):
            return Response(
                {"error": "You don't have permission to view this stream"},
                status=status.HTTP_403_FORBIDDEN,
            )

        participants = stream.participants.filter(left_at__isnull=True).select_related(
            "user"
        )
        serializer = StreamParticipantSerializer(participants, many=True)
        return Response(serializer.data)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def join(self, request, pk=None):
        """Join a live stream as viewer"""
        stream = self.get_object()

        if not stream.can_view(request.user):
            return Response(
                {"error": "You don't have permission to view this stream"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if user is banned
        active_ban = StreamBan.objects.filter(
            stream=stream, user=request.user, expires_at__gt=timezone.now()
        ).exists()

        if active_ban:
            return Response(
                {"error": "You are banned from this stream"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Create or update participant
        participant, created = StreamParticipant.objects.get_or_create(
            stream=stream, user=request.user, defaults={"joined_at": timezone.now()}
        )

        if not created and participant.left_at:
            participant.left_at = None
            participant.joined_at = timezone.now()
            participant.save()

        # Update viewer count using model method
        stream.update_viewer_count()

        return Response({"message": "Joined stream successfully"})

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def leave(self, request, pk=None):
        """Leave a live stream"""
        stream = self.get_object()

        try:
            participant = StreamParticipant.objects.get(
                stream=stream, user=request.user, left_at__isnull=True
            )
            participant.left_at = timezone.now()

            # Calculate watch time
            if participant.joined_at:
                watch_duration = timezone.now() - participant.joined_at
                participant.watch_time += watch_duration

            participant.save()

            # Update viewer count
            stream.update_viewer_count()

            return Response({"message": "Left stream successfully"})
        except StreamParticipant.DoesNotExist:
            return Response(
                {"error": "You are not currently in this stream"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def add_moderator(self, request, pk=None):
        """Add a user as moderator (streamer only)"""
        stream = self.get_object()

        if stream.streamer != request.user:
            return Response(
                {"error": "Only the streamer can add moderators"},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            user_to_mod = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Add or update participant as moderator
        participant, created = StreamParticipant.objects.get_or_create(
            stream=stream,
            user=user_to_mod,
            defaults={
                "role": StreamParticipant.ParticipantRole.MODERATOR,
                "joined_at": timezone.now(),
            },
        )

        if not created:
            participant.role = StreamParticipant.ParticipantRole.MODERATOR
            participant.save()

        return Response({"message": f"{user_to_mod.email} added as moderator"})

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def report(self, request, pk=None):
        """Report a stream for moderation"""
        stream = self.get_object()
        reason = request.data.get("reason", "")

        StreamModerationLog.objects.create(
            stream=stream,
            action="Stream reported",
            performed_by=request.user,
            target_user=stream.streamer,
            notes=f"Report reason: {reason}",
        )

        return Response({"message": "Stream reported successfully"})

    @action(detail=False, methods=["get"])
    def featured(self, request):
        """Get featured live streams"""
        featured_streams = self.get_queryset().filter(
            status=LiveStream.StreamStatus.LIVE, is_featured=True
        )
        serializer = self.get_serializer(featured_streams, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def categories(self, request):
        """Get all stream categories with counts"""
        from django.db.models import Count

        categories = (
            LiveStream.objects.filter(status=LiveStream.StreamStatus.LIVE)
            .values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        return Response(categories)


class StreamRecordingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StreamRecording.objects.all().select_related("stream")
    serializer_class = StreamRecordingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see recordings for streams they own or participated in
        return self.queryset.filter(
            Q(stream__streamer=self.request.user)
            | Q(stream__participants__user=self.request.user)
        ).distinct()


class StreamMessageViewSet(viewsets.ModelViewSet):
    queryset = StreamMessage.objects.all().select_related("user", "stream")
    serializer_class = StreamMessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsStreamParticipant]

    def get_queryset(self):
        queryset = self.queryset
        stream_id = self.request.query_params.get("stream")
        if stream_id:
            queryset = queryset.filter(stream_id=stream_id)

        # Only show non-moderated messages to moderators/streamers
        user = self.request.user
        if user.is_authenticated:
            stream = queryset.first().stream if queryset.exists() else None
            if stream and not (
                user == stream.streamer
                or StreamParticipant.objects.filter(
                    stream=stream,
                    user=user,
                    role=StreamParticipant.ParticipantRole.MODERATOR,
                ).exists()
            ):
                queryset = queryset.filter(is_moderated=False)

        return queryset.order_by("timestamp")

    def perform_create(self, serializer):
        stream = serializer.validated_data["stream"]

        # Check if user is banned
        if StreamBan.objects.filter(stream=stream, user=self.request.user).exists():
            raise serializers.ValidationError("You are banned from this stream")

        # Check if user is in the stream
        if not StreamParticipant.objects.filter(
            stream=stream, user=self.request.user, left_at__isnull=True
        ).exists():
            raise serializers.ValidationError(
                "You must be in the stream to send messages"
            )

        serializer.save(user=self.request.user)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def moderate(self, request, pk=None):
        """Moderate a message (streamer/moderator only)"""
        message = self.get_object()
        stream = message.stream

        # Check if user has moderation privileges
        if not (
            request.user == stream.streamer
            or StreamParticipant.objects.filter(
                stream=stream,
                user=request.user,
                role=StreamParticipant.ParticipantRole.MODERATOR,
            ).exists()
        ):
            return Response(
                {"error": "You don't have moderation privileges"},
                status=status.HTTP_403_FORBIDDEN,
            )

        message.is_moderated = True
        message.moderated_by = request.user
        message.save()

        return Response({"message": "Message moderated successfully"})

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def flag(self, request, pk=None):
        """Flag a message for moderation"""
        message = self.get_object()

        # Users can only flag messages in streams they can view
        if not message.stream.can_view(request.user):
            return Response(
                {"error": "You don't have permission to flag messages in this stream"},
                status=status.HTTP_403_FORBIDDEN,
            )

        message.flag_count += 1
        if message.flag_count >= 3:  # Auto-moderate after 3 flags
            message.is_flagged = True
            message.is_moderated = True
        message.save()

        return Response({"message": "Message flagged successfully"})


class StreamReactionViewSet(viewsets.ModelViewSet):
    queryset = StreamReaction.objects.all().select_related("user", "stream")
    serializer_class = StreamReactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsStreamParticipant]

    def get_queryset(self):
        queryset = self.queryset
        stream_id = self.request.query_params.get("stream")
        if stream_id:
            queryset = queryset.filter(stream_id=stream_id)
        return queryset

    def perform_create(self, serializer):
        stream = serializer.validated_data["stream"]

        # Check if user is in the stream
        if not StreamParticipant.objects.filter(
            stream=stream, user=self.request.user, left_at__isnull=True
        ).exists():
            raise serializers.ValidationError("You must be in the stream to react")

        # Use get_or_create to handle unique constraint
        reaction, created = StreamReaction.objects.get_or_create(
            stream=stream,
            user=self.request.user,
            reaction_type=serializer.validated_data["reaction_type"],
            defaults=serializer.validated_data,
        )

        if not created:
            # Update existing reaction
            for attr, value in serializer.validated_data.items():
                setattr(reaction, attr, value)
            reaction.save()

    def destroy(self, request, *args, **kwargs):
        """Allow users to remove their reactions"""
        instance = self.get_object()
        if instance.user != request.user:
            return Response(
                {"error": "You can only remove your own reactions"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class StreamBanViewSet(viewsets.ModelViewSet):
    queryset = StreamBan.objects.all().select_related("user", "banned_by", "stream")
    serializer_class = StreamBanSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = self.queryset
        stream_id = self.request.query_params.get("stream")
        if stream_id:
            queryset = queryset.filter(stream_id=stream_id)

        # Users can only see bans for streams they moderate
        user = self.request.user
        if user.is_authenticated:
            queryset = queryset.filter(
                Q(stream__streamer=user)
                | Q(
                    stream__participants__user=user,
                    stream__participants__role="moderator",
                )
            ).distinct()

        return queryset

    def perform_create(self, serializer):
        stream = serializer.validated_data["stream"]
        user_to_ban = serializer.validated_data["user"]

        # Check if current user can ban (streamer or moderator)
        if not (
            self.request.user == stream.streamer
            or StreamParticipant.objects.filter(
                stream=stream,
                user=self.request.user,
                role=StreamParticipant.ParticipantRole.MODERATOR,
            ).exists()
        ):
            raise serializers.ValidationError("You don't have permission to ban users")

        # Can't ban yourself
        if user_to_ban == self.request.user:
            raise serializers.ValidationError("You cannot ban yourself")

        # Can't ban the streamer
        if user_to_ban == stream.streamer:
            raise serializers.ValidationError("You cannot ban the streamer")

        serializer.save(banned_by=self.request.user)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def unban(self, request, pk=None):
        """Unban a user"""
        ban = self.get_object()
        stream = ban.stream

        # Check if current user can unban
        if not (
            request.user == stream.streamer
            or StreamParticipant.objects.filter(
                stream=stream,
                user=request.user,
                role=StreamParticipant.ParticipantRole.MODERATOR,
            ).exists()
        ):
            return Response(
                {"error": "You don't have permission to unban users"},
                status=status.HTTP_403_FORBIDDEN,
            )

        ban.delete()
        return Response({"message": "User unbanned successfully"})


class StreamAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StreamAnalytics.objects.all().select_related("stream")
    serializer_class = StreamAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see analytics for their own streams
        return self.queryset.filter(stream__streamer=self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get summary analytics for all user's streams"""
        streams = LiveStream.objects.filter(streamer=request.user)

        summary = {
            "total_streams": streams.count(),
            "total_live_streams": streams.filter(
                status=LiveStream.StreamStatus.LIVE
            ).count(),
            "total_views": sum(stream.total_views for stream in streams),
            "total_duration": sum(
                (
                    stream.duration.total_seconds()
                    for stream in streams
                    if stream.duration
                ),
                0,
            ),
            "average_viewers": streams.aggregate(avg=Count("viewer_count"))["avg"] or 0,
        }

        return Response(summary)
