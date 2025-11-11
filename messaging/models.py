from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class DirectMessage(models.Model):
    """
    One-to-one direct message between sender and recipient.
    For conversation grouping we use a deterministic group name derived from user ids.
    """
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages")
    # core
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to="messages/attachments/", null=True, blank=True)
    # reply support
    in_reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    created_at = models.DateTimeField(auto_now_add=True)
    delivered = models.BooleanField(default=False)  
    read = models.BooleanField(default=False)   
    deleted_by_sender = models.BooleanField(default=False)
    deleted_by_recipient = models.BooleanField(default=False)
    # optional: store conversation group snapshot (for quick queries)
    conversation_key = models.CharField(max_length=100, db_index=True, null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation_key", "-created_at"]),
            models.Index(fields=["sender", "recipient", "created_at"]),
        ]

    def __str__(self):
        return f"DM {self.id} from {self.sender} -> {self.recipient}"

    def save(self, *args, **kwargs):
        # Ensure deterministic conversation_key so both directions map to the same room
        try:
            a = int(getattr(self.sender, "id"))
            b = int(getattr(self.recipient, "id"))
            low, high = (a, b) if a <= b else (b, a)
            self.conversation_key = f"dm_{low}_{high}"
        except Exception:
            # fallback: pair ids as strings
            s1 = str(self.sender)
            s2 = str(self.recipient)
            self.conversation_key = f"dm_{min(s1,s2)}_{max(s1,s2)}"
        super().save(*args, **kwargs)


