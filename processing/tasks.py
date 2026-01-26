from django.db import transaction
from documents.models import Document, TextChunk, Section, Image
from .services import TextExtractor, MetadataExtractor, TextChunker, SectionExtractor
from .models import ProcessingLog
from .vector_service import VectorService
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process uploaded documents through the complete pipeline"""

    def __init__(self, document):
        self.document = document
        self.file_path = document.file.path

    def process(self):
        """Run the complete processing pipeline"""
        import logging
        import time
        logger = logging.getLogger(__name__)

        try:
            start_time = time.time()
            logger.info(f"Starting processing for document {self.document.id}: {self.document.file_name}")

            # Update document status
            self.document.status = 'processing'
            self.document.save()
            logger.info(f"Document status set to 'processing'")

            # 1. Text Extraction
            step_start = time.time()
            extracted_text = self._extract_text()
            step_time = time.time() - step_start
            logger.info(f"Text extraction completed in {step_time:.2f}s, extracted {len(extracted_text)} characters")

            if not extracted_text:
                raise Exception("Failed to extract text from document")

            # Store the complete extracted text
            self.document.extracted_text = extracted_text
            self.document.save()

            # 2. Metadata Extraction
            step_start = time.time()
            metadata = self._extract_metadata(extracted_text)
            self.document.metadata = metadata
            self.document.save()
            step_time = time.time() - step_start
            logger.info(f"Metadata extraction completed in {step_time:.2f}s")

            # 3. Text Chunking
            step_start = time.time()
            chunks = self._chunk_text(extracted_text)
            self._save_chunks(chunks)
            step_time = time.time() - step_start
            logger.info(f"Text chunking completed in {step_time:.2f}s, created {len(chunks)} chunks")

            # 4. Section Extraction
            step_start = time.time()
            sections = self._extract_sections(extracted_text)
            self._save_sections(sections)
            step_time = time.time() - step_start
            logger.info(f"Section extraction completed in {step_time:.2f}s, found {len(sections)} sections")

            # 5. Image Extraction (placeholder for now)
            # self._extract_images()

            # 6. Generate and Store Embeddings
            step_start = time.time()
            self._generate_embeddings()
            step_time = time.time() - step_start
            logger.info(f"Embedding generation completed in {step_time:.2f}s")

            # Mark as complete
            self.document.status = 'complete'
            self.document.save()

            total_time = time.time() - start_time
            logger.info(f"Document processing completed successfully in {total_time:.2f}s")
            return True

        except Exception as e:
            # Mark as failed
            self.document.status = 'failed'
            self.document.save()
            logger.error(f"Document processing failed: {str(e)}", exc_info=True)
            ProcessingLog.log_error('processing', str(e), self.document)
            return False

    def _extract_text(self):
        """Extract text from document"""
        import logging
        import time
        logger = logging.getLogger(__name__)

        ProcessingLog.log_start(self.document, 'text_extraction')
        step_start = time.time()

        file_extension = self.document.file_type.lower()
        logger.info(f"Extracting text from {file_extension} file: {self.file_path}")

        text = None

        if file_extension == 'pdf':
            logger.info("Using PDF text extraction")
            text = TextExtractor.extract_from_pdf(self.file_path)
        elif file_extension == 'docx':
            logger.info("Using DOCX text extraction")
            text = TextExtractor.extract_from_docx(self.file_path)
        elif file_extension == 'txt':
            logger.info("Using TXT text extraction")
            text = TextExtractor.extract_from_txt(self.file_path)

        step_time = time.time() - step_start
        if text:
            logger.info(f"Text extraction successful in {step_time:.2f}s, extracted {len(text)} characters")
            ProcessingLog.log_complete(self.document, 'text_extraction', {
                'text_length': len(text),
                'file_type': file_extension
            })
            return text
        else:
            logger.error(f"Text extraction failed for {file_extension} file - no text extracted")
            raise Exception(f"Failed to extract text from {file_extension} file")

    def _extract_metadata(self, text):
        """Extract metadata from text"""
        ProcessingLog.log_start(self.document, 'metadata_extraction')

        title = MetadataExtractor.extract_title(text, self.document.file_name)
        dates = MetadataExtractor.extract_dates(text)
        parties = MetadataExtractor.extract_parties(text)

        metadata = {
            'title': title,
            'dates': dates,
            'parties': parties,
            'extracted_at': datetime.now().isoformat(),
            'text_length': len(text)
        }

        ProcessingLog.log_complete(self.document, 'metadata_extraction', metadata)
        return metadata

    def _chunk_text(self, text):
        """Chunk text for processing"""
        logger.info("Starting text chunking process")
        ProcessingLog.log_start(self.document, 'chunking')

        try:
            chunker = TextChunker(chunk_size=1000, overlap=200)
            logger.info(f"Created TextChunker, text length: {len(text)}")
            chunks = chunker.chunk_text(text)
            logger.info(f"Chunking completed, created {len(chunks)} chunks")

            ProcessingLog.log_complete(self.document, 'chunking', {
                'chunk_count': len(chunks)
            })

            return chunks
        except Exception as e:
            logger.error(f"Error in chunking: {e}", exc_info=True)
            raise

    def _save_chunks(self, chunks):
        """Save text chunks to database"""
        logger.info(f"Starting to save {len(chunks)} chunks to database")
        try:
            with transaction.atomic():
                # Delete existing chunks
                logger.info("Deleting existing chunks")
                TextChunk.objects.filter(document=self.document).delete()

                # Create new chunks
                chunk_objects = []
                for i, chunk_data in enumerate(chunks):
                    chunk_objects.append(TextChunk(
                        document=self.document,
                        chunk_index=i,
                        start_offset=chunk_data['start_offset'],
                        end_offset=chunk_data['end_offset'],
                        text=chunk_data['text']
                    ))

                TextChunk.objects.bulk_create(chunk_objects)
                logger.info(f"Successfully saved {len(chunk_objects)} chunks to database")

        except Exception as e:
            logger.error(f"Error saving chunks: {e}", exc_info=True)
            raise

    def _extract_sections(self, text):
        """Extract sections from text"""
        logger.info("Starting section extraction")
        ProcessingLog.log_start(self.document, 'section_extraction')

        try:
            sections = SectionExtractor.extract_sections(text)
            logger.info(f"Section extraction completed, found {len(sections)} sections")
            return sections
        except Exception as e:
            logger.error(f"Error in section extraction: {e}", exc_info=True)
            raise

        ProcessingLog.log_complete(self.document, 'section_extraction', {
            'section_count': len(sections)
        })

        return sections

    def _save_sections(self, sections):
        """Save sections to database"""
        with transaction.atomic():
            # Delete existing sections
            Section.objects.filter(document=self.document).delete()

            # Create new sections
            section_objects = []
            for i, section_data in enumerate(sections):
                section_objects.append(Section(
                    document=self.document,
                    title=section_data.get('title', ''),
                    label=section_data.get('label', ''),
                    start_offset=section_data['start_offset'],
                    end_offset=section_data['end_offset'],
                    confidence=section_data.get('confidence', 0.0)
                ))

            Section.objects.bulk_create(section_objects)

    def _extract_images(self):
        """Extract images from document (placeholder)"""
        ProcessingLog.log_start(self.document, 'image_extraction')
        # TODO: Implement image extraction
        ProcessingLog.log_complete(self.document, 'image_extraction', {
            'image_count': 0
        })

    def _generate_embeddings(self):
        """Generate embeddings and store in vector database"""
        import logging
        import time
        logger = logging.getLogger(__name__)

        ProcessingLog.log_start(self.document, 'embeddings')
        step_start = time.time()

        try:
            logger.info("Initializing vector service")
            vector_service = VectorService()

            logger.info("Ensuring Qdrant collection exists")
            collection_start = time.time()
            vector_service.ensure_collection_exists()
            collection_time = time.time() - collection_start
            logger.info(f"Qdrant collection setup completed in {collection_time:.2f}s")

            # Store chunks in vector database
            logger.info("Starting to store document chunks in vector database")
            chunk_count = vector_service.store_document_chunks(self.document)

            step_time = time.time() - step_start
            logger.info(f"Embedding generation completed in {step_time:.2f}s, processed {chunk_count} chunks")
            ProcessingLog.log_complete(self.document, 'embeddings', {
                'chunks_processed': chunk_count
            })

        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}", exc_info=True)
            ProcessingLog.log_error('embeddings', str(e), self.document)
            raise