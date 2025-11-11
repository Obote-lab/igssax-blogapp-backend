from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL




class Comment(models.Model):
    """A comment on a post or another comment (threaded)."""

    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    content = models.TextField(blank=True) 
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on {self.post}"

    def get_nesting_level(self):
        """Calculate how deep this comment is nested"""
        level = 0
        parent = self.parent
        while parent is not None:
            level += 1
            parent = parent.parent
        return level

class Conversation(models.Model):
    """Chat-like conversation thread (like WhatsApp group)."""

    name = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="conversations_created"
    )
    participants = models.ManyToManyField(User, related_name="conversations")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name or f"Conversation {self.id}"


class ConversationMessage(models.Model):
    conversation = models.ForeignKey("Conversation", on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_by = models.ManyToManyField(User, related_name="read_messages", blank=True)
    delivered_to = models.ManyToManyField(User, related_name="delivered_messages", blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} - {self.content[:20]}"


class CommentAttachment(models.Model):
    """Supports multiple files or GIFs per comment."""
    comment = models.ForeignKey("Comment", on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="comments/", blank=True, null=True)
    gif_url = models.URLField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for Comment {self.comment.id}"

    @property
    def file_type(self):
        """Determine the type of attachment"""
        if self.gif_url:
            return 'gif'
        elif self.file:
            filename = self.file.name.lower()
            if any(ext in filename for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                return 'image'
            elif any(ext in filename for ext in ['.mp4', '.mov', '.avi', '.webm']):
                return 'video'
            else:
                return 'file'
        return 'unknown'