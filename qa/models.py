from django.conf import settings
from django.db import models


class QAHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    document_ids = models.JSONField(default=list, blank=True)
    chunk_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email}: {self.question[:50]}..."
