import mimetypes
from django.db.models import Max
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Avg, F, FloatField,Count, Q, Sum, Case, When
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django_filters.rest_framework import (DjangoFilterBackend, FilterSet,
                                           filters)
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from posts.querysets import visible_posts_for_user
from ..models import (
    Post, PostMedia, PostShare,
      PostView, Story, Tag,StoryComment,
      StoryReaction,PostTag, PostInsight, ContentModeration
    )
from users.models import Friendship
from django.utils import timezone
from .serializers import (PostCreateSerializer, PostSerializer,
                        PostShareSerializer, StorySerializer, TagSerializer, 
                        PostUpdateSerializer, ContentModerationSerializer, 
                            PostInsightSerializer,
                        BulkTagSerializer, BulkDeleteSerializer,
                        StoryFeedUserSerializer,StoryItemSerializer,
                        StoryCreateSerializer,StoryReaction,
                        StoryComment,StoryCommentSerializer,StoryReactionSerializer
                          )


# PERMISSIONS
class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user

# FILTERS
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


# POST VIEWSET
@extend_schema_view(
    list=extend_schema(summary="List all posts"),
    retrieve=extend_schema(summary="Retrieve a post"),
    create=extend_schema(summary="Create a post"),
    update=extend_schema(summary="Update a post"),
    partial_update=extend_schema(summary="Partially update a post"),
    destroy=extend_schema(summary="Delete a post"),
)
class PostViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend]
    filterset_class = PostFilter
    parser_classes = [MultiPartParser, FormParser]

    # Conditional permissions: public can see list/retrieve
    def get_permissions(self):
        if self.action in ["list", "retrieve", "my_posts"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]

    # Use conditional serializer
    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PostCreateSerializer
        return PostSerializer

    # Privacy-aware queryset
    def get_queryset(self):
        return (
            Post.objects.filter(is_deleted=False)
            .filter(visible_posts_for_user(self.request.user))
            .select_related("author", "author__profile")
            .prefetch_related("media", "tags")
            .annotate(
                comment_total=Count("comments", distinct=True),
                share_total=Count("shares", distinct=True),
            )
            .order_by("-created_at")
        )

    # Use get_object() override to enforce privacy safely
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(queryset, pk=self.kwargs["pk"])
        self.check_object_permissions(self.request, obj)
        return obj

    # Create post + broadcast websocket
    def perform_create(self, serializer):
        post = serializer.save(author=self.request.user)
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

    # MY POSTS
    @extend_schema(summary="List my posts", description="Retrieve posts created by authenticated user.",responses={200: PostSerializer(many=True)}, )
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_posts(self, request):
        posts = self.get_queryset().filter(author=request.user)
        page = self.paginate_queryset(posts)
        if page is not None:
            serializer = PostSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = PostSerializer(posts, many=True, context={"request": request})
        return Response(serializer.data)

    # ADD MEDIA
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def add_media(self, request, pk=None):
        post = self.get_object()
        if post.author != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)
        files = request.FILES.getlist("media_files")
        if not files:
            return Response(
                {"error": "No files uploaded"}, status=status.HTTP_400_BAD_REQUEST
            )
        for file in files:
            content_type, _ = mimetypes.guess_type(file.name)
            media_type = (
                "video" if content_type and "video" in content_type else "image"
            )
            PostMedia.objects.create(post=post, file=file, media_type=media_type)
        return Response(
            PostSerializer(post, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # RECORD POST VIEW
    @action(detail=True, methods=["post"])
    def view(self, request, pk=None):
        post = self.get_object()
        PostView.objects.get_or_create(
            post=post,
            user=request.user if request.user.is_authenticated else None,
            defaults={"ip_address": request.META.get("REMOTE_ADDR")},
        )
        return Response({"status": "view recorded"})
    

    def get_serializer_class(self):
        if self.action in ["create"]:
            return PostCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return PostUpdateSerializer
        elif self.action == "insights":
            return PostInsightSerializer
        return PostSerializer
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def tag_users(self, request, pk=None):
        """Tag users in a post"""
        post = self.get_object()
        if post.author != request.user:
            return Response(
                {"error": "Only the post author can tag users."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_ids = request.data.get('user_ids', [])
        tagged_users = []
        
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                # Check if already tagged
                if not PostTag.objects.filter(post=post, user=user).exists():
                    PostTag.objects.create(post=post, user=user)
                    tagged_users.append(user)
            except User.DoesNotExist:
                continue
        
        return Response({
            "success": f"Tagged {len(tagged_users)} users",
            "tagged_users": UserSerializer(tagged_users, many=True).data
        })
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def insights(self, request, pk=None):
        """Get post insights (author only)"""
        post = self.get_object()
        if post.author != request.user:
            return Response(
                {"error": "Only the post author can view insights."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        insight, created = PostInsight.objects.get_or_create(post=post)
        serializer = PostInsightSerializer(insight, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def flag(self, request, pk=None):
        """Flag a post for moderation"""
        post = self.get_object()
        reason = request.data.get('reason', 'other')
        
        # Check if already flagged by this user
        if ContentModeration.objects.filter(post=post, reported_by=request.user).exists():
            return Response(
                {"error": "You have already flagged this post."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        flag = ContentModeration.objects.create(
            post=post,
            reported_by=request.user,
            reason=reason
        )
        
        return Response({
            "success": "Post flagged for moderation",
            "flag_id": flag.id
        })
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def drafts(self, request):
        """Get user's draft posts"""
        drafts = Post.objects.filter(
            author=request.user,
            is_draft=True,
            is_deleted=False
        ).order_by('-saved_at')
        
        page = self.paginate_queryset(drafts)
        if page is not None:
            serializer = PostSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = PostSerializer(drafts, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def scheduled(self, request):
        """Get user's scheduled posts"""
        scheduled = Post.objects.filter(
            author=request.user,
            is_scheduled=True,
            is_deleted=False
        ).order_by('scheduled_for')
        
        page = self.paginate_queryset(scheduled)
        if page is not None:
            serializer = PostSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = PostSerializer(scheduled, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def bulk_tag(self, request):
        """Bulk tag posts"""
        serializer = BulkTagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        post_ids = serializer.validated_data['post_ids']
        tag_names = serializer.validated_data['tag_names']
        
        # Verify user owns these posts
        posts = Post.objects.filter(
            id__in=post_ids,
            author=request.user,
            is_deleted=False
        )
        
        if len(posts) != len(post_ids):
            return Response(
                {"error": "Some posts not found or you don't have permission."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        tags_created = 0
        for post in posts:
            for tag_name in tag_names:
                tag, created = Tag.objects.get_or_create(
                    name=tag_name.strip().lower()
                )
                post.tags.add(tag)
                if created:
                    tags_created += 1
        
        return Response({
            "success": f"Added tags to {len(posts)} posts",
            "tags_created": tags_created
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def bulk_delete(self, request):
        """Bulk delete posts"""
        serializer = BulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        post_ids = serializer.validated_data['post_ids']
        permanent = serializer.validated_data['permanent']
        
        posts = Post.objects.filter(
            id__in=post_ids,
            author=request.user
        )
        
        deleted_count = 0
        if permanent:
            # Actually delete from database
            deleted_count, _ = posts.delete()
        else:
            # Soft delete
            deleted_count = posts.update(is_deleted=True)
        
        return Response({
            "success": f"Deleted {deleted_count} posts",
            "permanent": permanent
        })


# STORY VIEWSET
@extend_schema_view(
    list=extend_schema(summary="List all stories"),
    create=extend_schema(summary="Create a story"),
    retrieve=extend_schema(summary="Retrieve a story"),
)
class StoryViewSet(viewsets.ModelViewSet):
    serializer_class = StorySerializer
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = StoryFilter

    def get_permissions(self):
        if self.action in ["list", "retrieve", "active", "feed"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user if self.request.user.is_authenticated else None
        qs = Story.objects.filter(expires_at__gt=now()).select_related("author")

        # Optional author filter
        author_id = self.request.query_params.get("author")
        if author_id:
            qs = qs.filter(author__id=author_id)

        if user:
            # Get friends IDs using the proper Friendship model
            # User is either requester OR receiver in ACCEPTED friendships
            friendships_as_requester = Friendship.objects.filter(
                requester=user,
                status=Friendship.Status.ACCEPTED
            ).values_list('receiver_id', flat=True)
            
            friendships_as_receiver = Friendship.objects.filter(
                receiver=user,
                status=Friendship.Status.ACCEPTED
            ).values_list('requester_id', flat=True)
            
            friend_ids = list(friendships_as_requester) + list(friendships_as_receiver)
            
            # Include user's own stories and friends' stories
            qs = qs.filter(Q(author__id__in=friend_ids) | Q(author=user))
        
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return StoryCreateSerializer
        return StorySerializer

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "media": {"type": "string", "format": "binary"}
                },
                "required": ["media"],
            }
        }
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        story = serializer.save(author=request.user)
        return Response(StorySerializer(story, context={"request": request}).data)


    @extend_schema(summary="List active stories")
    @action(detail=False, methods=["get"])
    def active(self, request):
        stories = self.get_queryset()
        serializer = self.get_serializer(stories, many=True)
        return Response(serializer.data)


    @extend_schema(summary="Stories feed for user and friends")
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated], url_path="feed")
    def feed(self, request):
        user = request.user
        now_ts = now()
        # Get all friends (both where user is requester or receiver)
        friendships_as_requester = Friendship.objects.filter(
            requester=user,
            status=Friendship.Status.ACCEPTED
        ).values_list('receiver_id', flat=True)
        
        friendships_as_receiver = Friendship.objects.filter(
            receiver=user,
            status=Friendship.Status.ACCEPTED
        ).values_list('requester_id', flat=True)
        
        friend_ids = list(friendships_as_requester) + list(friendships_as_receiver)
        stories = (
            Story.objects
            .filter(
                expires_at__gt=now_ts,
                author_id__in=friend_ids + [user.id],
            )
            .select_related("author", "author__profile")
            .order_by("author_id", "-created_at")
        )
        grouped = {}
        for story in stories:
            uid = story.author_id

            if uid not in grouped:
                grouped[uid] = {
                    "user": StoryFeedUserSerializer(
                        story.author,
                        context={"request": request},
                    ).data,
                    "stories": [],
                    "latest_story_at": story.created_at,
                }

            grouped[uid]["stories"].append(
                StoryItemSerializer(
                    story,
                    context={"request": request},
                ).data
            )
        feed = list(grouped.values())

        # Put logged-in user first
        feed.sort(
            key=lambda x: (
                x["user"]["id"] != user.id,
                -x["latest_story_at"].timestamp(),
            )
        )

        return Response(feed)
    

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def vote_poll(self, request, pk=None):
        """Vote on a story poll"""
        story = self.get_object()
        
        if story.story_type != 'poll':
            return Response(
                {"error": "This story is not a poll."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        vote = request.data.get('vote')  # 'a' or 'b'
        if vote not in ['a', 'b']:
            return Response(
                {"error": "Vote must be 'a' or 'b'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # In production, you'd track individual votes with a StoryVote model
        # This is a simplified version
        if vote == 'a':
            story.poll_votes_a = F('poll_votes_a') + 1
        else:
            story.poll_votes_b = F('poll_votes_b') + 1
        
        story.save()
        story.refresh_from_db()
        
        return Response({
            "success": "Vote recorded",
            "poll_results": {
                'option_a': story.poll_votes_a,
                'option_b': story.poll_votes_b,
                'total': story.poll_votes_a + story.poll_votes_b
            }
        })
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def seen_by(self, request, pk=None):
        """Get list of users who have seen the story"""
        story = self.get_object()
        
        # Only author can see who viewed their story
        if story.author != request.user:
            return Response(
                {"error": "Only the story author can see viewers."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        views = StoryView.objects.filter(story=story).select_related('user')
        viewers = [view.user for view in views if view.user]
        
        return Response(
            UserSerializer(viewers, many=True, context={'request': request}).data
        )


class StoryReactionViewSet(viewsets.ModelViewSet):
    """Handle story reactions"""
    serializer_class = StoryReactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return StoryReaction.objects.filter(
            story_id=self.kwargs.get('story_pk'),
            story__expires_at__gt=timezone.now()
        )
    
    def perform_create(self, serializer):
        story = get_object_or_404(Story, id=self.kwargs.get('story_pk'))
        
        # Delete existing reaction if exists
        StoryReaction.objects.filter(
            story=story,
            user=self.request.user
        ).delete()
        
        serializer.save(story=story, user=self.request.user)


class StoryCommentViewSet(viewsets.ModelViewSet):
    """Handle story comments"""
    serializer_class = StoryCommentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return StoryComment.objects.filter(
            story_id=self.kwargs.get('story_pk'),
            story__expires_at__gt=timezone.now()
        ).select_related('author', 'author__profile')
    
    def perform_create(self, serializer):
        story = get_object_or_404(Story, id=self.kwargs.get('story_pk'))
        serializer.save(story=story, author=self.request.user)

# TAGS
class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all().order_by("name")
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

# POST SHARES
class PostShareViewSet(viewsets.ModelViewSet):
    queryset = PostShare.objects.all().select_related("post", "user")
    serializer_class = PostShareSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        post_id = self.request.data.get("post")
        share_type = self.request.data.get("share_type", "feed")
        post = get_object_or_404(Post, id=post_id)
        user = self.request.user
        if PostShare.objects.filter(
            post=post, user=user, share_type=share_type
        ).exists():
            raise serializers.ValidationError("You already shared this post.")
        serializer.save(user=user, post=post)



# Add at the end of viewsets.py

class ContentModerationViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for moderators to review flagged content"""
    serializer_class = ContentModerationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only staff can view moderation queue
        if self.request.user.is_staff:
            return ContentModeration.objects.filter(
                status='pending'
            ).select_related('post', 'reported_by', 'reviewed_by')
        return ContentModeration.objects.none()
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        """Approve a post (dismiss flag)"""
        if not request.user.is_staff:
            return Response(
                {"error": "Only staff can moderate content."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        flag = self.get_object()
        flag.status = 'approved'
        flag.reviewed_by = request.user
        flag.reviewed_at = timezone.now()
        flag.save()
        
        return Response({"success": "Post approved."})
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def remove(self, request, pk=None):
        """Remove a flagged post"""
        if not request.user.is_staff:
            return Response(
                {"error": "Only staff can moderate content."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        flag = self.get_object()
        flag.status = 'removed'
        flag.reviewed_by = request.user
        flag.reviewed_at = timezone.now()
        flag.save()
        
        # Mark post as deleted
        flag.post.is_deleted = True
        flag.post.save()
        
        return Response({"success": "Post removed."})


class PostInsightViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for post analytics/insights"""
    serializer_class = PostInsightSerializer
    permission_classes = [IsAuthenticated]
    

    queryset = PostInsight.objects.none()

    
    def get_queryset(self):
        # Users can only see insights for their own posts
        return PostInsight.objects.filter(
            post__author=self.request.user,
            post__is_deleted=False
        ).select_related('post')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary insights for all user posts"""
        insights = PostInsight.objects.filter(
            post__author=request.user,
            post__is_deleted=False
        ).aggregate(
            total_reach=Sum('reach'),
            total_engagement=Sum('engagement'),
            total_shares=Sum('shares'),
            avg_engagement_rate=Avg(
                Case(
                    When(reach__gt=0, then=F('engagement') * 100.0 / F('reach')),
                    default=0,
                    output_field=FloatField()
                )
            )
        )
        
        return Response(insights)