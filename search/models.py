from django.conf import settings
from django.db import models


class SearchHistory(models.Model):
    SEARCH_TYPES = [
        ('keyword', 'Keyword Search'),
        ('semantic', 'Semantic Search'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    search_type = models.CharField(max_length=20, choices=SEARCH_TYPES)
    query = models.TextField()
    filters = models.JSONField(default=dict, blank=True)
    results_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["search_type"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email}: {self.search_type} - {self.query[:50]}"
