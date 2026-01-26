import os
import logging
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)


class AnswerService:
    """Generate answers using LLM based on search results"""

    def __init__(self):
        # Initialize OpenAI client for OpenRouter
        self.openai_client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL
        )
        self.llm_model = settings.OPENROUTER_LLM_MODEL

    def generate_answer(self, query, context_chunks, document_title=None):
        """Generate an answer based on the query and context chunks"""
        try:
            # Prepare context from chunks
            context = self._prepare_context(context_chunks)

            # Create prompt
            prompt = self._create_prompt(query, context, document_title)

            # Generate answer
            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that answers questions based on the provided document context. Be concise, accurate, and directly address the user's question. Use only the information provided in the context."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.3
            )

            answer = response.choices[0].message.content.strip()
            return answer

        except Exception as e:
            logger.error(f"Error generating answer: {e}", exc_info=True)
            return None

    def _prepare_context(self, chunks):
        """Prepare context from search result chunks"""
        context_parts = []

        for chunk in chunks:
            # Use the snippet from search results (these are the matching chunks from vector search)
            context_parts.append(f"Excerpt: {chunk['snippet']}")

        return "\n\n".join(context_parts)

    def _create_prompt(self, query, context, document_title):
        """Create a prompt for the LLM"""
        prompt = f"""Question: {query}

Document Context:
{context}

"""

        if document_title:
            prompt += f"Document: {document_title}\n\n"

        prompt += """Please answer the question based on the provided context. If the context doesn't contain enough information to fully answer the question, please say so and provide what information is available."""

        return prompt