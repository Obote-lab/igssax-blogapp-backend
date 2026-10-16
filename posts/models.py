from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field


User = settings.AUTH_USER_MODEL

class Post(models.Model):
    PRIVACY_CHOICES = [
        ("public", "Public"),
        ("friends_only", "Friends Only"),
        ("only_me", "Only Me"),
    ]
    POST_TYPES = [
        ('status', 'Status'),
        ('photo', 'Photo'),
        ('video', 'Video'),
        ('link', 'Link'),
        ('event', 'Event'),
        ('poll', 'Poll'),
        ('offer', 'Offer'),
    ]
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    content = models.TextField(blank=True)
    privacy = models.CharField(max_length=20, choices=PRIVACY_CHOICES, default="public")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField("Tag", related_name="posts", blank=True)
    share_count = models.PositiveIntegerField(default=0, editable=False)
    views_count = models.PositiveIntegerField(default=0, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    # visibility_cached_for = models.JSONField(default=dict, blank=True)
    post_type = models.CharField(max_length=20, choices=POST_TYPES, default='status')
    # Link preview
    link_url = models.URLField(blank=True)
    link_title = models.CharField(max_length=200, blank=True)
    link_description = models.TextField(blank=True)
    link_image = models.URLField(blank=True)
    # Location
    location = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    is_scheduled = models.BooleanField(default=False)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    # Drafts
    is_draft = models.BooleanField(default=False)
    saved_at = models.DateTimeField(null=True, blank=True)
    # Versioning
    edited_count = models.PositiveIntegerField(default=0)
    last_edited_at = models.DateTimeField(null=True, blank=True)
    edit_history = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['privacy', '-created_at']),
            models.Index(fields=['is_deleted', '-created_at']),
            models.Index(fields=['scheduled_for', 'is_scheduled']),
        ]

    def __str__(self):
        return f"Post by {self.author} ({self.created_at.strftime('%Y-%m-%d')})"


class PostMedia(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="posts/media/")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.media_type} for Post {self.post.id}"

class PostTag(models.Model):
    """Tag users in posts"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    position_x = models.FloatField(null=True, blank=True) 
    position_y = models.FloatField(null=True, blank=True)
    tagged_at = models.DateTimeField(auto_now_add=True)

class Story(models.Model):
    # Add story types
    STORY_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('text', 'Text'),
        ('poll', 'Poll'),
        ('question', 'Question'),
    ]
   
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stories")
    media = models.FileField(upload_to="stories/")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True, db_index=True)
    reactions_count = models.PositiveIntegerField(default=0, editable=False)
    comments_count = models.PositiveIntegerField(default=0, editable=False)
    views_count = models.PositiveIntegerField(default=0, editable=False)

    story_type = models.CharField(max_length=20, choices=STORY_TYPES, default='image')
    # Text stories
    background_color = models.CharField(max_length=20, blank=True)
    text_content = models.TextField(blank=True)
    # Poll stories
    poll_question = models.CharField(max_length=200, blank=True)
    poll_option_a = models.CharField(max_length=100, blank=True)
    poll_option_b = models.CharField(max_length=100, blank=True)
    # Engagement metrics
    reply_count = models.PositiveIntegerField(default=0)
    poll_votes_a = models.PositiveIntegerField(default=0)
    poll_votes_b = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    def is_active(self):
        return self.expires_at > timezone.now()

    def __str__(self):
        return f"Story by {self.author} (expires {self.expires_at})"


class StoryReaction(models.Model):
    """Reactions to stories (like, love, wow, etc.)"""
    REACTION_TYPES = [
        ('like', '👍 Like'),
        ('love', '❤️ Love'),
        ('wow', '😮 Wow'),
        ('haha', '😂 Haha'),
        ('sad', '😢 Sad'),
        ('angry', '😠 Angry'),
    ]
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_reactions')
    reaction_type = models.CharField(max_length=20, choices=REACTION_TYPES, default='like')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ('story', 'user') 
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user} reacted {self.reaction_type} to story {self.story.id}"

class StoryComment(models.Model):
    """Comments on stories"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='story_comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']  
    def __str__(self):
        return f"Comment by {self.author} on story {self.story.id}"


class StoryView(models.Model):
    """Track who viewed which story (for analytics and "seen by")"""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='views')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='story_views')
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('story', 'user')  
        indexes = [
            models.Index(fields=['story', 'user']),
            models.Index(fields=['viewed_at']),
        ]
    
    def __str__(self):
        return f"View by {self.user} on story {self.story.id}"

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True)
    display_name = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name
        self.name = self.name.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.display_name}"

class PostShare(models.Model):
    SHARE_TYPES = [
        ("feed", "Share to Feed"),
        ("message", "Share via Message"),
        ("external", "External Link"),
    ]
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shared_posts")
    share_type = models.CharField(max_length=20, choices=SHARE_TYPES, default="feed")
    shared_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ("post", "user", "share_type")

    def __str__(self):
        return f"{self.user} shared {self.post} ({self.share_type})"

class PostView(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(User,on_delete=models.SET_NULL, null=True, blank=True,related_name="post_views",)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["post", "user"]),
            models.Index(fields=["post", "ip_address"]),
            models.Index(fields=["viewed_at"]),
        ]
    def __str__(self):
        return f"View on Post {self.post_id}"


# Add to models.py
class PostVisibility(models.Model):
    """
    Granular privacy control (like Facebook's 'Friends except...', 'Custom')
    """
    post = models.OneToOneField(Post, on_delete=models.CASCADE)
    allowed_users = models.ManyToManyField(User, related_name='visible_posts', blank=True)
    restricted_users = models.ManyToManyField(User, related_name='restricted_posts', blank=True)
    
class VisibilityCache(models.Model):
    """Cache visibility calculations"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    can_view = models.BooleanField()
    cached_at = models.DateTimeField(auto_now=True)

class ContentModeration(models.Model):
    """Flag inappropriate content"""
    FLAG_REASONS = [
        ('spam', 'Spam'),
        ('hate_speech', 'Hate Speech'),
        ('harassment', 'Harassment'),
        ('violence', 'Violence'),
        ('nudity', 'Nudity'),
        ('copyright', 'Copyright'),
        ('other', 'Other'),
    ]
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    reported_by = models.ForeignKey( User,on_delete=models.CASCADE,related_name="reports_made"   )
    reason = models.CharField(max_length=20, choices=FLAG_REASONS)
    status = models.CharField(max_length=20, default='pending')
    reviewed_by = models.ForeignKey( User,null=True, blank=True,on_delete=models.CASCADE,related_name="reports_reviewed" )
    reviewed_at = models.DateTimeField(null=True, blank=True)

class PostInsight(models.Model):
    """Igssax insights"""
    post = models.OneToOneField(Post, on_delete=models.CASCADE)
    reach = models.PositiveIntegerField(default=0)
    engagement = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    # Demographics (simplified)
    male_viewers = models.PositiveIntegerField(default=0)
    female_viewers = models.PositiveIntegerField(default=0)
    age_18_24 = models.PositiveIntegerField(default=0)
    age_25_34 = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Insights for Post {self.post.id}"