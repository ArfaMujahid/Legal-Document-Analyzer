from django.conf import settings
from django.db import models


class ErrorLog(models.Model):
    """Processing errors, kept for LOG_RETENTION_DAYS (see cleanup_expired)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='error_logs',
    )
    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='error_logs',
    )
    stage = models.CharField(max_length=50)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['created_at'])]

    def __str__(self):
        return f"[{self.stage}] {self.message[:80]}"
