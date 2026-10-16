# posts/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count, F, Q
from django.contrib import messages
from .models import (
    Post, PostMedia, Story, Tag, PostShare, 
    PostView, StoryReaction, StoryComment, StoryView
)

# ==================== INLINES ====================
class PostMediaInline(admin.TabularInline):
    model = PostMedia
    extra = 1
    readonly_fields = ['preview', 'uploaded_at']
    
    def preview(self, obj):
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height: 50px; max-width: 50px;" /></a>',
                obj.file.url,
                obj.file.url
            )
        return "-"
    preview.short_description = "Preview"


class StoryReactionInline(admin.TabularInline):
    model = StoryReaction
    extra = 0
    readonly_fields = ['created_at']
    raw_id_fields = ['user']


class StoryCommentInline(admin.TabularInline):
    model = StoryComment
    extra = 0
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['author']


class StoryViewInline(admin.TabularInline):
    model = StoryView
    extra = 0
    readonly_fields = ['viewed_at']
    raw_id_fields = ['user']


class PostViewInline(admin.TabularInline):
    model = PostView
    extra = 0
    readonly_fields = ['viewed_at']
    raw_id_fields = ['user']


class PostShareInline(admin.TabularInline):
    model = PostShare
    extra = 0
    readonly_fields = ['shared_at']
    raw_id_fields = ['user']

# ==================== ADMIN FILTERS ====================
class ActiveStoryFilter(admin.SimpleListFilter):
    title = 'Active status'
    parameter_name = 'active'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active Stories'),
            ('expired', 'Expired Stories'),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'active':
            return queryset.filter(expires_at__gt=now)
        if self.value() == 'expired':
            return queryset.filter(expires_at__lte=now)


class HasMediaFilter(admin.SimpleListFilter):
    title = 'Has Media'
    parameter_name = 'has_media'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Has Media'),
            ('no', 'No Media'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.annotate(media_count=Count('media')).filter(media_count__gt=0)
        if self.value() == 'no':
            return queryset.annotate(media_count=Count('media')).filter(media_count=0)


class PopularPostFilter(admin.SimpleListFilter):
    title = 'Popularity'
    parameter_name = 'popular'

    def lookups(self, request, model_admin):
        return (
            ('popular', 'Popular (100+ views)'),
            ('viral', 'Viral (500+ views)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'popular':
            return queryset.filter(views_count__gte=100)
        if self.value() == 'viral':
            return queryset.filter(views_count__gte=500)

# ==================== MODEL ADMINS ====================
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'author', 'content_preview', 'privacy', 
        'views_count', 'share_count', 'comment_count', 
        'has_media', 'is_deleted', 'created_at'
    ]
    list_filter = [
        'privacy', 'is_deleted', 'created_at', 
        HasMediaFilter, PopularPostFilter
    ]
    search_fields = [
        'content', 'author__email', 'author__first_name', 
        'author__last_name', 'tags__name'
    ]
    readonly_fields = [
        'views_count', 'share_count', 'comment_count', 
        'created_at', 'updated_at', 'interaction_stats'
    ]
    raw_id_fields = ['author']
    inlines = [PostMediaInline, PostViewInline, PostShareInline]
    actions = ['mark_as_deleted', 'restore_posts', 'export_posts']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('author', 'content', 'privacy', 'tags')
        }),
        ('Counters', {
            'fields': ('views_count', 'share_count', 'comment_count')
        }),
        ('Status', {
            'fields': ('is_deleted', 'created_at', 'updated_at')
        }),
        ('Statistics', {
            'fields': ('interaction_stats',),
            'classes': ('collapse',)
        }),
    )

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = "Content"

    def has_media(self, obj):
        return obj.media.exists()
    has_media.boolean = True
    has_media.short_description = "Media"

    def comment_count(self, obj):
        return obj.comments.count()
    comment_count.short_description = "Comments"

    def interaction_stats(self, obj):
        views = obj.views_count
        shares = obj.share_count
        comments = obj.comments.count()
        total = views + shares + comments
        
        if total == 0:
            return "No interactions yet"
        
        return format_html("""
            <strong>Total Interactions:</strong> {}<br>
            • Views: {} ({:.1f}%)<br>
            • Shares: {} ({:.1f}%)<br>
            • Comments: {} ({:.1f}%)
        """, total, views, (views/total)*100, shares, (shares/total)*100, 
           comments, (comments/total)*100)
    interaction_stats.short_description = "Interaction Statistics"

    def mark_as_deleted(self, request, queryset):
        updated = queryset.update(is_deleted=True)
        self.message_user(
            request, 
            f"{updated} post(s) marked as deleted", 
            messages.SUCCESS
        )
    mark_as_deleted.short_description = "Mark selected posts as deleted"

    def restore_posts(self, request, queryset):
        updated = queryset.update(is_deleted=False)
        self.message_user(
            request, 
            f"{updated} post(s) restored", 
            messages.SUCCESS
        )
    restore_posts.short_description = "Restore selected posts"

    def export_posts(self, request, queryset):
        # This would typically export to CSV/JSON
        self.message_user(
            request,
            f"Export functionality would process {queryset.count()} posts",
            messages.INFO
        )
    export_posts.short_description = "Export selected posts"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'media', 'tags', 'comments'
        ).annotate(
            share_count_field=Count('shares', distinct=True)
        )


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'author', 'media_preview', 'is_active', 
        'reactions_count', 'comments_count', 'views_count',
        'created_at', 'expires_at', 'time_remaining'
    ]
    list_filter = [
        ActiveStoryFilter, 'created_at', 
        ('author', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = [
        'author__email', 'author__first_name', 'author__last_name'
    ]
    readonly_fields = [
        'reactions_count', 'comments_count', 'views_count',
        'created_at', 'expires_at', 'media_preview_large',
        'engagement_rate', 'popular_reactions'
    ]
    raw_id_fields = ['author']
    inlines = [StoryReactionInline, StoryCommentInline, StoryViewInline]
    actions = ['cleanup_expired', 'recalculate_counts']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('author', 'media', 'media_preview_large')
        }),
        ('Timing', {
            'fields': ('created_at', 'expires_at')
        }),
        ('Counters', {
            'fields': ('reactions_count', 'comments_count', 'views_count')
        }),
        ('Analytics', {
            'fields': ('engagement_rate', 'popular_reactions'),
            'classes': ('collapse',)
        }),
    )

    def media_preview(self, obj):
        if obj.media:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height: 40px; max-width: 40px;" /></a>',
                obj.media.url,
                obj.media.url
            )
        return "-"
    media_preview.short_description = "Media"

    def media_preview_large(self, obj):
        if obj.media:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height: 200px; max-width: 200px;" /></a>',
                obj.media.url,
                obj.media.url
            )
        return "No media"
    media_preview_large.short_description = "Media Preview"

    def is_active(self, obj):
        return obj.is_active()
    is_active.boolean = True
    is_active.short_description = "Active"

    def time_remaining(self, obj):
        if not obj.is_active():
            return "Expired"
        
        remaining = obj.expires_at - timezone.now()
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        if remaining.days > 0:
            return f"{remaining.days}d {hours}h"
        return f"{hours}h {minutes}m"
    time_remaining.short_description = "Time Left"

    def engagement_rate(self, obj):
        views = obj.views_count or 1  # Avoid division by zero
        total_interactions = obj.reactions_count + obj.comments_count
        rate = (total_interactions / views) * 100
        return f"{rate:.1f}%"
    engagement_rate.short_description = "Engagement Rate"

    def popular_reactions(self, obj):
        reactions = StoryReaction.objects.filter(story=obj).values(
            'reaction_type'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:3]
        
        if not reactions:
            return "No reactions yet"
        
        reaction_text = []
        for r in reactions:
            emoji_map = {
                'like': '👍',
                'love': '❤️',
                'wow': '😮',
                'haha': '😂',
                'sad': '😢',
                'angry': '😠'
            }
            emoji = emoji_map.get(r['reaction_type'], r['reaction_type'])
            reaction_text.append(f"{emoji} {r['count']}")
        
        return " • ".join(reaction_text)
    popular_reactions.short_description = "Top Reactions"

    def cleanup_expired(self, request, queryset):
        expired = queryset.filter(expires_at__lte=timezone.now())
        count = expired.count()
        expired.delete()
        self.message_user(
            request,
            f"Cleaned up {count} expired stories",
            messages.SUCCESS
        )
    cleanup_expired.short_description = "Delete expired stories"

    def recalculate_counts(self, request, queryset):
        for story in queryset:
            story.reactions_count = story.reactions.count()
            story.comments_count = story.comments.count()
            story.views_count = story.views.count()
            story.save(update_fields=[
                'reactions_count', 'comments_count', 'views_count'
            ])
        
        self.message_user(
            request,
            f"Recalculated counts for {queryset.count()} stories",
            messages.SUCCESS
        )
    recalculate_counts.short_description = "Recalculate counters"


@admin.register(StoryReaction)
class StoryReactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'story', 'reaction_type_emoji', 'created_at']
    list_filter = ['reaction_type', 'created_at']
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'story__author__email'
    ]
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'story']

    def reaction_type_emoji(self, obj):
        emoji_map = {
            'like': '👍',
            'love': '❤️',
            'wow': '😮',
            'haha': '😂',
            'sad': '😢',
            'angry': '😠'
        }
        emoji = emoji_map.get(obj.reaction_type, obj.reaction_type)
        return f"{emoji} {obj.get_reaction_type_display()}"
    reaction_type_emoji.short_description = "Reaction"


@admin.register(StoryComment)
class StoryCommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'author', 'story', 'content_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = [
        'content', 'author__email', 'author__first_name', 'author__last_name',
        'story__author__email'
    ]
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['author', 'story']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = "Comment"


@admin.register(StoryView)
class StoryViewAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'story', 'viewed_at']
    list_filter = ['viewed_at']
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'story__author__email'
    ]
    readonly_fields = ['viewed_at']
    raw_id_fields = ['user', 'story']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'display_name', 'posts_count', 'created_at']
    search_fields = ['name', 'display_name']
    readonly_fields = ['created_at']
    actions = ['merge_tags']

    def posts_count(self, obj):
        return obj.posts.count()
    posts_count.short_description = "Posts"

    def merge_tags(self, request, queryset):
        if queryset.count() < 2:
            self.message_user(
                request,
                "Select at least 2 tags to merge",
                messages.ERROR
            )
            return
        
        primary_tag = queryset.first()
        other_tags = queryset.exclude(id=primary_tag.id)
        
        from django.db import transaction
        with transaction.atomic():
            for tag in other_tags:
                # Update all posts using this tag
                for post in tag.posts.all():
                    post.tags.remove(tag)
                    post.tags.add(primary_tag)
                
                # Delete the tag
                tag.delete()
        
        self.message_user(
            request,
            f"Merged {other_tags.count()} tags into '{primary_tag.name}'",
            messages.SUCCESS
        )
    merge_tags.short_description = "Merge selected tags"


@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):
    list_display = ['id', 'post', 'media_type', 'preview', 'uploaded_at']
    list_filter = ['media_type', 'uploaded_at']
    search_fields = ['post__content', 'post__author__email']
    readonly_fields = ['uploaded_at', 'preview_large']
    raw_id_fields = ['post']

    def preview(self, obj):
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height: 30px; max-width: 30px;" /></a>',
                obj.file.url,
                obj.file.url
            )
        return "-"
    preview.short_description = "Preview"

    def preview_large(self, obj):
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="max-height: 300px; max-width: 300px;" /></a>',
                obj.file.url,
                obj.file.url
            )
        return "No file"
    preview_large.short_description = "Large Preview"


@admin.register(PostShare)
class PostShareAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'post', 'share_type', 'shared_at']
    list_filter = ['share_type', 'shared_at']
    search_fields = [
        'user__email', 'post__content', 'post__author__email'
    ]
    readonly_fields = ['shared_at']
    raw_id_fields = ['user', 'post']


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'post', 'ip_address', 'viewed_at']
    list_filter = ['viewed_at']
    search_fields = [
        'user__email', 'post__content', 'ip_address'
    ]
    readonly_fields = ['viewed_at']
    raw_id_fields = ['user', 'post']


# ==================== ADMIN SITE CONFIG ====================
# Optional: Customize the admin site header and title
admin.site.site_header = "IGSSAX Admin"
admin.site.site_title = "IGSSAX Administration"
admin.site.index_title = "Welcome to IGSSAX Admin Panel"
