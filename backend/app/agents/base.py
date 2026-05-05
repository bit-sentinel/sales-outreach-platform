"""
Base agent class – shared LLM configuration, retry logic, cost tracking.
"""

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings


class BaseAgent:
    """Shared infrastructure for all AI agents."""

    def __init__(self):
        self.settings = get_settings()

    def get_llm(self, model: str | None = None, temperature: float = 0.7) -> ChatAnthropic:
        """Get the primary LLM (Anthropic Claude)."""
        return ChatAnthropic(
            model=model or self.settings.anthropic_model,
            temperature=temperature,
            api_key=self.settings.anthropic_api_key,
            max_retries=self.settings.llm_max_retries,
        )

    def get_fast_llm(self, temperature: float = 0.3) -> ChatAnthropic:
        """Get the fast/cheap LLM for lightweight tasks."""
        return ChatAnthropic(
            model=self.settings.anthropic_fast_model,
            temperature=temperature,
            api_key=self.settings.anthropic_api_key,
            max_retries=self.settings.llm_max_retries,
        )

    def get_fallback_llm(self, temperature: float = 0.7) -> ChatOpenAI:
        """Get the fallback LLM (OpenAI)."""
        return ChatOpenAI(
            model=self.settings.openai_model,
            temperature=temperature,
            api_key=self.settings.openai_api_key,
            max_retries=self.settings.llm_max_retries,
            request_timeout=self.settings.llm_request_timeout,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def invoke_with_retry(self, chain: Any, input_data: Any) -> Any:
        """Invoke a chain with retry logic."""
        return await chain.ainvoke(input_data)
