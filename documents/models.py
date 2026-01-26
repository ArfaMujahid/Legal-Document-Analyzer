from django.conf import settings
from django.db import models


class Document(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('extracting_text', 'Extracting Text'),
        ('chunking', 'Chunking'),
        ('extracting_sections', 'Extracting Sections'),
        ('extracting_images', 'Extracting Images'),
        ('generating_embeddings', 'Generating Embeddings'),
        ('complete', 'Complete'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='documents/%Y/%m/', null=True, blank=True)
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    file_size = models.BigIntegerField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='uploaded')
    upload_time = models.DateTimeField(auto_now_add=True)
    delete_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)
    extracted_text = models.TextField(blank=True, null=True)  # Store complete extracted text

    class Meta:
        indexes = [
            models.Index(fields=["user", "delete_at"]),
        ]

    def __str__(self):
        return f"{self.file_name}"


class DocumentFile(models.Model):
    document = models.OneToOneField(Document, on_delete=models.CASCADE)
    storage_path = models.CharField(max_length=500)
    checksum = models.CharField(max_length=128, blank=True)

    def __str__(self):
        return f"{self.document_id}"


class TextChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    chunk_index = models.IntegerField()
    start_offset = models.IntegerField()
    end_offset = models.IntegerField()
    text = models.TextField()

    class Meta:
        indexes = [
            models.Index(fields=["document", "chunk_index"]),
        ]

    def __str__(self):
        return f"{self.document_id}:{self.chunk_index}"


class Section(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True)
    label = models.CharField(max_length=100, blank=True)
    start_offset = models.IntegerField()
    end_offset = models.IntegerField()
    confidence = models.FloatField(default=0.0)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        indexes = [
            models.Index(fields=["document", "start_offset"]),
        ]

    def __str__(self):
        return f"{self.document_id}:{self.label or self.title}"


class Image(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    image_index = models.IntegerField()
    page_number = models.IntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=50)
    file_size = models.BigIntegerField()
    width = models.IntegerField()
    height = models.IntegerField()
    storage_path = models.CharField(max_length=500)

    class Meta:
        indexes = [
            models.Index(fields=["document", "image_index"]),
        ]

    def __str__(self):
        return f"{self.document_id}:{self.image_index}"
