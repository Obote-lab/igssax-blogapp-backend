import mimetypes
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils.timezone import now
from django_filters.rest_framework import (DjangoFilterBackend, FilterSet,
                                           filters)
from drf_spectacular.utils import extend_schema, extend_schema_view
from requests import post
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..models import Post, PostMedia, Story, Tag, PostShare
from .serializers import (PostCreateSerializer, PostSerializer,
                          StorySerializer, TagSerializer, PostShareSerializer)


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user


class PostFilter(FilterSet):
    from_date = filters.DateFilter(field_name="created_at", lookup_expr="gte")
    to_date = filters.DateFilter(field_name="created_at", lookup_expr="lte")
    tag = filters.CharFilter(field_name="tags__name", lookup_expr="iexact")

    class Meta:
        model = Post
        fields = ["author", "tag", "from_date", "to_date"]


class StoryFilter(FilterSet):
    active_only = filters.BooleanFilter(method="filter_active")

    class Meta:
        model = Story
        fields = ["author", "active_only"]

    def filter_active(self, queryset, name, value):
        if value:
            return queryset.filter(expires_at__gt=now())
        return queryset


@extend_schema_view(
    list=extend_schema(summary="List all posts"),
    retrieve=extend_schema(summary="Retrieve a post"),
    create=extend_schema(summary="Create a post"),
    update=extend_schema(summary="Update a post"),
    partial_update=extend_schema(summary="Partially update a post"),
    destroy=extend_schema(summary="Delete a post"),
)

class PostViewSet(viewsets.ModelViewSet):
    queryset = (
        Post.objects.all()
        .select_related("author")
        .prefetch_related(
            "media", 
            "tags", 
            "comments__author__profile",
            "comments__replies__author__profile",
            "comments__replies__replies__author__profile"
        )
    )
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PostFilter
    parser_classes = [MultiPartParser, FormParser]

    # KEEP all your existing methods below exactly as they are
    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PostCreateSerializer
        return PostSerializer

    def perform_create(self, serializer):
        """Create a new post and broadcast via WebSocket"""
        post = serializer.save(author=self.request.user)

        # WebSocket Broadcast
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            "posts_group",
            {
                "type": "send_new_post",
                "data": {
                    "action": "new_post",
                    "post": PostSerializer(
                        post, context={"request": self.request}
                    ).data,
                },
            },
        )

    # KEEP all your existing actions (@action methods) exactly as they are
    @extend_schema(
        summary="List my posts",
        description="Retrieve all posts created by the authenticated user.",
        responses={200: PostSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def my_posts(self, request):
        posts = self.get_queryset().filter(author=request.user)
        page = self.paginate_queryset(posts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(posts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def add_media(self, request, pk=None):
        """Add media to an existing post"""
        post = self.get_object()
        files = request.FILES.getlist("media_files")

        if not files:
            return Response(
                {"error": "No files provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        for file in files:
            content_type, _ = mimetypes.guess_type(file.name)
            media_type = (
                "video" if content_type and "video" in content_type else "image"
            )
            PostMedia.objects.create(post=post, file=file, media_type=media_type)

        return Response({"success": f"{len(files)} media files added"})






@extend_schema_view(
    list=extend_schema(summary="List all stories"),
    create=extend_schema(summary="Create a story"),
    retrieve=extend_schema(summary="Retrieve a story"),
)
class StoryViewSet(viewsets.ModelViewSet):
    queryset = Story.objects.all().select_related("author")
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = StoryFilter

    def perform_create(self, serializer):
        story = serializer.save(author=self.request.user)

        # Optional: Broadcast new story to WebSocket clients
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            "stories_group",
            {
                "type": "send_new_story",
                "data": {
                    "action": "new_story",
                    "story": StorySerializer(
                        story, context={"request": self.request}
                    ).data,
                },
            },
        )

    @extend_schema(
        summary="List active stories",
        description="Retrieve only active (non-expired) stories.",
        responses={200: StorySerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def active(self, request):
        stories = self.queryset.filter(expires_at__gt=now())
        serializer = self.get_serializer(stories, many=True)
        return Response(serializer.data)


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None



class PostShareViewSet(viewsets.ModelViewSet):
    queryset = PostShare.objects.all()
    serializer_class = PostShareSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        post_id = self.request.data.get("post")
        share_type = self.request.data.get("share_type", "feed")
        post = Post.objects.get(id=post_id)
        user = self.request.user

        # prevent duplicate shares per type
        existing = PostShare.objects.filter(post=post, user=user, share_type=share_type).first()
        if existing:
            return Response({"detail": "You already shared this post."}, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(user=user)

        # update share count
        post.share_count = PostShare.objects.filter(post=post).count()
        post.save(update_fields=["share_count"])