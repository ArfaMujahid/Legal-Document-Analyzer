from django.db import models
from django.conf import settings


class ProcessingLog(models.Model):
    """Track processing stages and errors"""

    STAGES = [
        ('text_extraction', 'Text Extraction'),
        ('ocr', 'OCR Processing'),
        ('metadata_extraction', 'Metadata Extraction'),
        ('chunking', 'Text Chunking'),
        ('section_extraction', 'Section Extraction'),
        ('image_extraction', 'Image Extraction'),
        ('embeddings', 'Embeddings Generation'),
        ('vector_storage', 'Vector Storage'),
    ]

    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name='processing_logs'
    )
    stage = models.CharField(max_length=50, choices=STAGES)
    status = models.CharField(max_length=20, choices=[
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ])
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', 'stage']),
            models.Index(fields=['status', 'created_at']),
        ]

    @classmethod
    def log_start(cls, document, stage):
        """Log the start of a processing stage"""
        return cls.objects.create(
            document=document,
            stage=stage,
            status='started',
            message=f"Started {stage}"
        )

    @classmethod
    def log_complete(cls, document, stage, details=None):
        """Log the completion of a processing stage"""
        return cls.objects.create(
            document=document,
            stage=stage,
            status='completed',
            message=f"Completed {stage}",
            details=details or {}
        )

    @classmethod
    def log_error(cls, stage, message, document=None):
        """Log a processing error"""
        from logs.models import ErrorLog
        ErrorLog.objects.create(
            user=document.user if document else None,
            document=document,
            stage=stage,
            message=message
        )

        if document:
            return cls.objects.create(
                document=document,
                stage=stage,
                status='failed',
                message=f"Failed {stage}: {message}"
            )
        return None