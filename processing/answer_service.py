import logging
from openai import OpenAI, APIError
from django.conf import settings

logger = logging.getLogger(__name__)


class AnswerService:
    """Generate answers using LLM based on search results"""

    def __init__(self):
        # Initialize OpenAI client for OpenRouter. No SDK retries: on a rate
        # limit we move straight to the next model instead of waiting.
        self.openai_client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            max_retries=0,
            timeout=30.0,
        )
        self.llm_model = settings.OPENROUTER_LLM_MODEL
        # Primary model first, then fallbacks (free models are often rate-limited).
        self.models = [
            m for m in [self.llm_model, *settings.OPENROUTER_FALLBACK_MODELS] if m
        ]

    def generate_answer(self, query, context_chunks, document_title=None):
        """Generate an answer based on the query and context chunks.

        Tries each configured model in order and returns the first non-empty
        answer, or None if every model fails.
        """
        context = self._prepare_context(context_chunks)
        prompt = self._create_prompt(query, context, document_title)
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that answers questions based on the provided document context. Be concise, accurate, and directly address the user's question. Use only the information provided in the context."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        for model in self.models:
            try:
                response = self.openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=500,
                    temperature=0.3
                )
                answer = (response.choices[0].message.content or "").strip()
                if answer:
                    logger.info(f"Answer generated with {model}")
                    return answer
                logger.warning(f"{model} returned an empty answer, trying next model")
            except APIError as e:
                # Rate limits, provider outages, unknown model ids: try the next model.
                status = getattr(e, "status_code", None)
                logger.warning(f"{model} failed ({status or type(e).__name__}), trying next model")
            except Exception as e:
                logger.error(f"Error generating answer with {model}: {e}", exc_info=True)
                return None

        logger.error(f"No answer: all models failed ({', '.join(self.models) or 'none configured'})")
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