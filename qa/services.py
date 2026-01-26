import json
from openai import OpenAI
from django.conf import settings
from documents.models import TextChunk, Document
from processing.vector_service import VectorService
from .models import QAHistory
import re


class QAService:
    """Handle question answering with citations using RAG"""

    def __init__(self):
        # Initialize OpenAI client for OpenRouter
        self.openai_client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL
        )
        self.llm_model = settings.OPENROUTER_LLM_MODEL
        self.vector_service = VectorService()

    def answer_question(self, user, question, document_ids=None):
        """
        Answer a question using retrieved evidence with citations

        Args:
            user: User object
            question: Question string
            document_ids: Optional list of document IDs to scope search

        Returns:
            dict with answer and citations
        """
        try:
            # 1. Retrieve relevant chunks
            relevant_chunks = self._retrieve_evidence(user, question, document_ids)

            if not relevant_chunks:
                return {
                    'answer': "I couldn't find relevant information in your documents to answer this question.",
                    'citations': [],
                    'evidence_insufficient': True
                }

            # 2. Generate answer with citations
            answer_data = self._generate_answer_with_citations(question, relevant_chunks)

            # 3. Save to history
            self._save_qa_history(user, question, answer_data, document_ids)

            return answer_data

        except Exception as e:
            return {
                'answer': f"An error occurred while processing your question: {str(e)}",
                'citations': [],
                'error': True
            }

    def _retrieve_evidence(self, user, question, document_ids=None, max_chunks=10):
        """Retrieve relevant chunks using semantic and keyword search"""
        chunks = []

        # 1. Semantic search
        try:
            semantic_results = self.vector_service.search_similar_chunks(
                query_text=question,
                user_id=user.id,
                document_id=document_ids[0] if document_ids and len(document_ids) == 1 else None,
                limit=max_chunks
            )
            chunks.extend(semantic_results)
        except Exception as e:
            print(f"Semantic search failed: {e}")

        # 2. Keyword search as fallback
        if len(chunks) < max_chunks:
            keyword_chunks = self._keyword_search(user, question, document_ids, max_chunks - len(chunks))
            # Add only new chunks (avoid duplicates)
            existing_ids = {c['chunk_id'] for c in chunks}
            for chunk in keyword_chunks:
                if chunk['chunk_id'] not in existing_ids:
                    chunks.append(chunk)

        # Sort by relevance (semantic score first, then recency)
        chunks.sort(key=lambda x: (-x.get('score', 0), x.get('document_upload_time', '')))

        return chunks[:max_chunks]

    def _keyword_search(self, user, question, document_ids, limit):
        """Perform keyword search as fallback"""
        from django.db.models import Q

        # Extract key terms from question
        key_terms = self._extract_key_terms(question)

        # Build query
        chunks_query = Q(document__user=user)

        if document_ids:
            chunks_query &= Q(document_id__in=document_ids)

        # Search for key terms
        term_query = Q()
        for term in key_terms:
            term_query |= Q(text__icontains=term)

        chunks = TextChunk.objects.filter(chunks_query & term_query).select_related('document')[:limit]

        results = []
        for chunk in chunks:
            results.append({
                'chunk_id': chunk.id,
                'document_id': chunk.document.id,
                'text': chunk.text,
                'start_offset': chunk.start_offset,
                'end_offset': chunk.end_offset,
                'chunk_index': chunk.chunk_index,
                'document_title': chunk.document.title or chunk.document.file_name,
                'document_upload_time': chunk.document.upload_time.isoformat(),
                'score': 0.5  # Default score for keyword matches
            })

        return results

    def _extract_key_terms(self, question):
        """Extract key terms from question for keyword search"""
        # Simple keyword extraction - remove common words
        stop_words = {
            'what', 'where', 'when', 'why', 'how', 'is', 'are', 'was', 'were',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'be', 'have', 'has', 'had', 'do',
            'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
            'can', 'must', 'shall', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }

        # Extract words longer than 2 characters
        words = re.findall(r'\b\w{3,}\b', question.lower())
        key_terms = [word for word in words if word not in stop_words]

        # Return unique terms
        return list(set(key_terms))

    def _generate_answer_with_citations(self, question, chunks):
        """Generate answer with citations using LLM"""
        # Prepare context with chunks
        context = self._prepare_context(chunks)

        # Create prompt for LLM
        prompt = f"""You are a legal document assistant. Answer the following question based ONLY on the provided context. If the context doesn't contain enough information to answer the question, say "I don't have enough information to answer this question."

Context:
{context}

Question: {question}

Instructions:
1. Answer based only on the provided context
2. Include citations in the format [Source X] where X is the chunk number
3. Be precise and factual
4. If multiple chunks provide relevant information, cite all of them

Answer:"""

        try:
            # Generate answer
            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are a helpful legal document assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1  # Low temperature for factual answers
            )

            answer = response.choices[0].message.content

            # Extract citations
            citations = self._extract_citations_from_answer(answer, chunks)

            return {
                'answer': answer,
                'citations': citations,
                'evidence_insufficient': "I don't have enough information" in answer
            }

        except Exception as e:
            return {
                'answer': f"Failed to generate answer: {str(e)}",
                'citations': [],
                'error': True
            }

    def _prepare_context(self, chunks):
        """Prepare context string from chunks"""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(
                f"[Source {i}] From {chunk['document_title']}:\n{chunk['text']}\n"
            )
        return "\n".join(context_parts)

    def _extract_citations_from_answer(self, answer, chunks):
        """Extract citation information from answer"""
        citations = []
        citation_pattern = r'\[Source (\d+)\]'

        # Find all citation references
        matches = re.findall(citation_pattern, answer)

        for match in set(matches):  # Use set to avoid duplicates
            chunk_index = int(match) - 1  # Convert to 0-based index
            if 0 <= chunk_index < len(chunks):
                chunk = chunks[chunk_index]
                citations.append({
                    'chunk_id': chunk['chunk_id'],
                    'document_id': chunk['document_id'],
                    'document_title': chunk['document_title'],
                    'start_offset': chunk['start_offset'],
                    'end_offset': chunk['end_offset'],
                    'chunk_index': chunk['chunk_index'],
                    'reference': f"[Source {match}]"
                })

        return citations

    def _save_qa_history(self, user, question, answer_data, document_ids):
        """Save Q&A interaction to history"""
        QAHistory.objects.create(
            user=user,
            question=question,
            answer=answer_data['answer'],
            citations=json.dumps([
                {
                    'chunk_id': c['chunk_id'],
                    'document_id': c['document_id'],
                    'start_offset': c['start_offset'],
                    'end_offset': c['end_offset']
                } for c in answer_data['citations']
            ]),
            document_ids=document_ids or [],
            chunk_ids=[c['chunk_id'] for c in answer_data['citations']]
        )