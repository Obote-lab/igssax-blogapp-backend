from django.db.models import F
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import (
    StoryReaction, StoryComment, StoryView, Story, 
    Post, PostView, PostShare, ContentModeration,
    PostTag, PostInsight, Story
)


# ========== POST SIGNALS ==========

@receiver(post_save, sender=PostView)
def handle_post_view_created(sender, instance, created, **kwargs):
    """
    Increment Post.views_count ONLY when a new PostView is created.
    Also update PostInsight if exists.
    """
    if not created:
        return

    # Update post views count
    Post.objects.filter(id=instance.post_id, is_deleted=False).update(
        views_count=F("views_count") + 1
    )
    
    # Update PostInsight reach if exists
    try:
        insight = PostInsight.objects.get(post_id=instance.post_id)
        insight.reach = F('reach') + 1
        insight.save(update_fields=['reach'])
    except PostInsight.DoesNotExist:
        pass


@receiver(post_delete, sender=PostView)
def handle_post_view_deleted(sender, instance, **kwargs):
    """
    Decrement Post.views_count if a PostView is removed.
    """
    Post.objects.filter(
        id=instance.post_id, is_deleted=False, views_count__gt=0
    ).update(views_count=F("views_count") - 1)


@receiver(post_save, sender=PostShare)
def handle_post_share_created(sender, instance, created, **kwargs):
    """
    Update share count and insights when a post is shared.
    """
    if not created:
        return
    
    Post.objects.filter(id=instance.post_id).update(
        share_count=F("share_count") + 1
    )
    
    # Update PostInsight
    try:
        insight = PostInsight.objects.get(post_id=instance.post_id)
        insight.shares = F('shares') + 1
        insight.save(update_fields=['shares'])
    except PostInsight.DoesNotExist:
        pass


@receiver(post_save, sender=PostTag)
def notify_tagged_user(sender, instance, created, **kwargs):
    """
    Send notification when user is tagged in a post.
    """
    if created:
        from notifications.models import Notification
        Notification.objects.create(
            recipient=instance.user,
            actor=instance.post.author,
            verb='tagged you in a post',
            target=instance.post,
            notification_type='tag'
        )


@receiver(post_save, sender=Post)
def create_post_insight(sender, instance, created, **kwargs):
    """
    Create PostInsight entry when a post is created.
    """
    if created and not instance.is_draft:
        PostInsight.objects.create(post=instance)


@receiver(pre_save, sender=Post)
def track_post_edits(sender, instance, **kwargs):
    """
    Track post edits in edit_history.
    """
    if instance.pk:
        try:
            old = Post.objects.get(pk=instance.pk)
            if old.content != instance.content:
                # Add to edit history
                if not instance.edit_history:
                    instance.edit_history = []
                
                instance.edit_history.append({
                    'old_content': old.content,
                    'new_content': instance.content,
                    'edited_at': timezone.now().isoformat(),
                    'edited_by': instance.author.id
                })
                instance.edited_count = len(instance.edit_history)
                instance.last_edited_at = timezone.now()
        except Post.DoesNotExist:
            pass


# ========== STORY SIGNALS ==========

@receiver(post_save, sender=StoryReaction)
def update_story_reactions_count(sender, instance, created, **kwargs):
    """Update reactions count when a reaction is added/removed"""
    if created:
        Story.objects.filter(id=instance.story_id).update(
            reactions_count=F('reactions_count') + 1
        )
    elif instance.story:
        # If reaction is updated (not deleted), recalculate
        count = StoryReaction.objects.filter(story=instance.story).count()
        Story.objects.filter(id=instance.story_id).update(
            reactions_count=count
        )


@receiver(post_delete, sender=StoryReaction)
def decrement_story_reactions_count(sender, instance, **kwargs):
    """Decrement reactions count when a reaction is deleted"""
    if instance.story:
        Story.objects.filter(
            id=instance.story_id, 
            reactions_count__gt=0
        ).update(
            reactions_count=F('reactions_count') - 1
        )


@receiver(post_save, sender=StoryComment)
def update_story_comments_count(sender, instance, created, **kwargs):
    """Update comments count when a comment is added/removed"""
    if created:
        Story.objects.filter(id=instance.story_id).update(
            comments_count=F('comments_count') + 1
        )


@receiver(post_delete, sender=StoryComment)
def decrement_story_comments_count(sender, instance, **kwargs):
    """Decrement comments count when a comment is deleted"""
    if instance.story:
        Story.objects.filter(
            id=instance.story_id, 
            comments_count__gt=0
        ).update(
            comments_count=F('comments_count') - 1
        )


@receiver(post_save, sender=StoryView)
def update_story_views_count(sender, instance, created, **kwargs):
    """Update views count when a story is viewed"""
    if created:
        Story.objects.filter(id=instance.story_id).update(
            views_count=F('views_count') + 1
        )


@receiver(post_save, sender=Story)
def handle_story_poll_vote(sender, instance, created, **kwargs):
    """
    Handle poll story votes.
    Triggered when Story.save() is called after updating poll votes.
    """
    if not created and instance.story_type == 'poll':
        # Recalculate poll percentages
        total_votes = instance.poll_votes_a + instance.poll_votes_b
        if total_votes > 0:
            instance.poll_percentage_a = (instance.poll_votes_a / total_votes) * 100
            instance.poll_percentage_b = (instance.poll_votes_b / total_votes) * 100
            instance.save(update_fields=['poll_percentage_a', 'poll_percentage_b'])


# ========== CONTENT MODERATION SIGNALS ==========

@receiver(post_save, sender=ContentModeration)
def handle_content_flag(sender, instance, created, **kwargs):
    """
    Handle content flagging - notify admins when content is reported.
    """
    if created:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Notify admins (simplified - in production use proper notification system)
        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            from notifications.models import Notification
            Notification.objects.create(
                recipient=admin,
                actor=instance.reported_by,
                verb=f'reported a post for {instance.get_reason_display()}',
                target=instance.post,
                notification_type='moderation'
            )


# ========== CLEANUP SIGNALS ==========

@receiver(post_save, sender=Post)
def cleanup_expired_scheduled_posts(sender, instance, **kwargs):
    """
    Publish scheduled posts when their time arrives.
    This would typically be handled by a cron job, but this is a fallback.
    """
    if (instance.is_scheduled and 
        instance.scheduled_for and 
        instance.scheduled_for <= timezone.now() and
        not instance.is_deleted):
        instance.is_scheduled = False
        instance.save(update_fields=['is_scheduled'])
        
        # Notify followers about new post
        from notifications.models import Notification
        from users.models import Follow
        
        followers = Follow.objects.filter(following=instance.author).select_related('follower')
        for follow in followers:
            Notification.objects.create(
                recipient=follow.follower,
                actor=instance.author,
                verb='published a new post',
                target=instance,
                notification_type='post'
            )


# Auto-create VisibilityCache entries for frequently accessed posts
@receiver(post_save, sender=Post)
def warm_visibility_cache(sender, instance, created, **kwargs):
    """
    Pre-cache visibility for friends when a new post is created.
    This improves performance for friend-only posts.
    """
    if created and instance.privacy == 'friends_only':
        from users.models import Friendship
        from .models import VisibilityCache
        
        # Get friends who should see this post
        friendships = Friendship.objects.filter(
            Q(requester=instance.author, status='accepted') |
            Q(receiver=instance.author, status='accepted')
        )
        
        friends = []
        for friendship in friendships:
            friend = friendship.requester if friendship.receiver == instance.author else friendship.receiver
            friends.append(friend)
        
        # Create cache entries
        cache_entries = [
            VisibilityCache(post=instance, user=friend, can_view=True)
            for friend in friends
        ]
        VisibilityCache.objects.bulk_create(cache_entries)