from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from documents.models import Document, TextChunk, Section, Image, DocumentFile
from processing.vector_service import VectorService
from logs.models import ErrorLog
import os


class Command(BaseCommand):
    help = 'Clean up expired documents and logs'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup process...')

        # Clean up expired documents
        expired_docs = Document.objects.filter(delete_at__lte=timezone.now())
        self.stdout.write(f'Found {expired_docs.count()} expired documents')

        for doc in expired_docs:
            self.stdout.write(f'Cleaning up document: {doc.file_name}')

            # Delete file from storage
            try:
                doc_file = DocumentFile.objects.filter(document=doc).first()
                if doc_file and os.path.exists(doc_file.storage_path):
                    os.remove(doc_file.storage_path)
                    self.stdout.write('  - Deleted file from storage')
            except Exception as e:
                self.stdout.write(f'  - Error deleting file: {e}')

            # Delete vectors from Qdrant
            try:
                vector_service = VectorService()
                vector_service.delete_document_vectors(doc.id)
                self.stdout.write('  - Deleted vectors from Qdrant')
            except Exception as e:
                self.stdout.write(f'  - Error deleting vectors: {e}')

            # Delete document and related records
            doc.delete()
            self.stdout.write('  - Deleted document and related records')

        # Clean up old error logs (older than 90 days)
        log_cutoff = timezone.now() - timedelta(days=90)
        old_logs = ErrorLog.objects.filter(created_at__lt=log_cutoff)
        log_count = old_logs.count()
        old_logs.delete()

        if log_count > 0:
            self.stdout.write(f'Deleted {log_count} old error log entries')

        self.stdout.write(self.style.SUCCESS('Cleanup completed successfully!'))