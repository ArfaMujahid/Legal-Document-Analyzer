import os
# from openai import OpenAI  # Commented out - using local embeddings instead
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, PayloadSchemaType
from django.conf import settings
from documents.models import TextChunk, Document
import json
import numpy as np
from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Process-wide singletons: the embedding model takes seconds to load, and
# embedded (local-mode) Qdrant allows only one client per storage folder.
_embedding_model = None
_qdrant_client = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


def get_qdrant_client():
    """Qdrant Cloud/server when QDRANT_URL is set, otherwise embedded on-disk storage."""
    global _qdrant_client
    if _qdrant_client is None:
        if settings.QDRANT_URL:
            _qdrant_client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=10.0,
            )
        else:
            _qdrant_client = QdrantClient(path=str(settings.QDRANT_LOCAL_PATH))
    return _qdrant_client


class VectorService:
    """Handle vector embeddings and storage with Qdrant"""

    def __init__(self):
        self.embedding_model = get_embedding_model()
        self.embedding_dimension = 384  # all-MiniLM-L6-v2 produces 384-dimensional vectors
        self.qdrant_client = get_qdrant_client()
        self.collection_name = "document_chunks"

    def ensure_collection_exists(self):
        """Create Qdrant collection if it doesn't exist"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.info(f"Checking if collection '{self.collection_name}' exists")
            collections = self.qdrant_client.get_collections()
            print("COLLECTIONS")
            print(collections)
            exists = any(
                collection.name == self.collection_name
                for collection in collections.collections
            )

            if not exists:
                logger.info(f"Creating new collection '{self.collection_name}'")
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self._get_embedding_dimension(),
                        distance=Distance.COSINE
                    )
                )

                # Create indexes for document_id and user_id
                try:
                    self.qdrant_client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="document_id",
                        field_schema=PayloadSchemaType.INTEGER
                    )
                    logger.info("Created index for document_id")
                except Exception as e:
                    logger.warning(f"Could not create index for document_id: {e}")

                try:
                    self.qdrant_client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="user_id",
                        field_schema=PayloadSchemaType.INTEGER
                    )
                    logger.info("Created index for user_id")
                except Exception as e:
                    logger.warning(f"Could not create index for user_id: {e}")

                logger.info(f"Successfully created collection with indexes: {self.collection_name}")
            else:
                logger.info(f"Collection '{self.collection_name}' already exists")
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}", exc_info=True)
            raise

    def _get_embedding_dimension(self):
        """Get the dimension of embeddings from the model"""
        # Return the known dimension for all-MiniLM-L6-v2
        return self.embedding_dimension

    def generate_embedding(self, text):
        """Generate embedding for text using local SentenceTransformer"""
        import logging
        import time
        logger = logging.getLogger(__name__)

        try:
            start_time = time.time()
            logger.debug(f"Generating embedding for text of length {len(text)}")

            # Generate embedding locally
            embedding = self.embedding_model.encode(text, normalize_embeddings=True)

            api_time = time.time() - start_time
            logger.debug(f"Local embedding generation completed in {api_time:.2f}s")

            return embedding.tolist()  # Convert numpy array to list
        except Exception as e:
            logger.error(f"Error generating embedding: {e}", exc_info=True)
            raise

    def store_document_chunks(self, document):
        """Store all chunks of a document in Qdrant"""
        import logging
        import time
        logger = logging.getLogger(__name__)

        chunks = TextChunk.objects.filter(document=document)
        logger.info(f"Found {len(chunks)} chunks to process for document {document.id}")

        points = []
        embedding_start = time.time()

        for i, chunk in enumerate(chunks):
            # Generate embedding
            chunk_start = time.time()
            embedding = self.generate_embedding(chunk.text)
            chunk_time = time.time() - chunk_start

            if i == 0:
                logger.info(f"First embedding generated in {chunk_time:.2f}s")
            elif i == 1:
                logger.info(f"Second embedding generated in {chunk_time:.2f}s")
            elif i % 5 == 0:
                logger.info(f"Generated embedding {i+1}/{len(chunks)} in {chunk_time:.2f}s")

            # Create point for Qdrant
            point = PointStruct(
                id=chunk.id,  # Use integer ID instead of string
                vector=embedding,
                payload={
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "user_id": document.user.id,
                    "text": chunk.text,
                    "start_offset": chunk.start_offset,
                    "end_offset": chunk.end_offset,
                    "chunk_index": chunk.chunk_index
                }
            )
            points.append(point)

        embedding_time = time.time() - embedding_start
        logger.info(f"All {len(chunks)} embeddings generated in {embedding_time:.2f}s")

        # Batch upsert to Qdrant
        if points:
            upsert_start = time.time()
            logger.info(f"Starting batch upsert of {len(points)} points to Qdrant")
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            upsert_time = time.time() - upsert_start
            logger.info(f"Qdrant upsert completed in {upsert_time:.2f}s")
            return len(points)
        return 0

    def search_similar_chunks(self, query_text, user_id, document_id=None, limit=10):
        """Search for similar chunks using semantic search"""
        # Generate embedding for query
        query_embedding = self.generate_embedding(query_text)

        # Build filter - if searching within a specific document, only filter by document_id
        if document_id:
            filter_conditions = {"must": [{"key": "document_id", "match": {"value": document_id}}]}
        else:
            # For global search, filter by user_id (but this requires index)
            filter_conditions = {"must": [{"key": "user_id", "match": {"value": user_id}}]}

        # Search in Qdrant with more results to allow for deduplication
        search_result = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=Filter(**filter_conditions),
            limit=limit * 2,  # Get more results to filter duplicates
            score_threshold=0.3  # Minimum similarity score
        ).points

        # Format and deduplicate results
        results = []
        seen_texts = set()

        for hit in search_result:
            chunk_text = hit.payload["text"].strip()

            # Skip very short or very long chunks
            if len(chunk_text) < 20 or len(chunk_text) > 2000:
                continue

            # Skip if we've seen very similar text before (deduplication)
            text_hash = self._get_text_hash(chunk_text)
            if text_hash in seen_texts:
                continue

            # Additional similarity check for overlapping content
            is_duplicate = False
            for existing_result in results:
                if self._are_chunks_similar(chunk_text, existing_result["text"]):
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_texts.add(text_hash)
                results.append({
                    "chunk_id": hit.payload["chunk_id"],
                    "document_id": hit.payload["document_id"],
                    "text": chunk_text,
                    "start_offset": hit.payload["start_offset"],
                    "end_offset": hit.payload["end_offset"],
                    "chunk_index": hit.payload["chunk_index"],
                    "score": hit.score
                })

                # Stop if we have enough results
                if len(results) >= limit:
                    break

        return results

    def _get_text_hash(self, text):
        """Generate a hash for text to identify duplicates"""
        import hashlib
        # Normalize text for comparison (remove extra spaces, lowercase)
        normalized = ' '.join(text.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _are_chunks_similar(self, text1, text2, threshold=0.8):
        """Check if two chunks are too similar (overlap)"""
        # Simple similarity check based on common words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        similarity = intersection / union if union > 0 else 0

        # Also check for length similarity (very different lengths are probably not duplicates)
        length_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2))

        return similarity > threshold and length_ratio > 0.5

    def delete_document_vectors(self, document_id):
        """Delete all vectors for a document"""
        # Get all chunk IDs for this document
        from documents.models import TextChunk
        chunk_ids = list(TextChunk.objects.filter(document_id=document_id).values_list('id', flat=True))

        if chunk_ids:
            # Delete by point IDs instead of filtering
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=chunk_ids
            )

    def get_user_vector_count(self, user_id):
        """Get count of vectors for a user"""
        filter_conditions = {
            "must": [
                {"key": "user_id", "match": {"value": user_id}}
            ]
        }

        result = self.qdrant_client.count(
            collection_name=self.collection_name,
            count_filter=Filter(**filter_conditions)
        )
        return result.count