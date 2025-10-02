from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class DirectMessage(models.Model):
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_messages"
    )
    content = models.TextField(blank=True)
    post_url = models.URLField(blank=True, null=True)  # 🔹 To attach post link
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"From {self.sender} to {self.recipient}"
