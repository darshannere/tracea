"""RCA backends: disabled, ollama, openai, anthropic."""
import os
from abc import ABC, abstractmethod

import httpx

from tracea.server.rca.models import RCABackendConfig


class RCABackend(ABC):
    """Abstract RCA backend. All methods are async."""

    @abstractmethod
    async def analyze(self, prompt: str | None = None, max_tokens: int = 2048, json_mode: bool = False) -> str:
        """Returns RCA text content, or raises on failure.

        Args:
            json_mode: If True, request structured JSON output from the LLM.
                       Not all backends support this natively; unsupported
                       backends fall back to standard text output.
        """
        ...


class OpenAIBackend(RCABackend):
    """OpenAI-compatible backend (supports OpenAI cloud, Ollama, etc.)."""

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        self.model = model or "gpt-4o"
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    async def analyze(self, prompt: str | None = None, max_tokens: int = 2048, json_mode: bool = False) -> str:
        """Call OpenAI chat completions API."""
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a DevOps root-cause analyst."},
                {"role": "user", "content": prompt or ""},
            ],
            "stream": False,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
            
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class AnthropicBackend(RCABackend):
    """Anthropic cloud backend. Supports custom base_url for Anthropic-compatible APIs."""

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        self.model = model or "claude-sonnet-4-20250514"
        self.api_key = api_key
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")

    async def analyze(self, prompt: str | None = None, max_tokens: int = 2048, json_mode: bool = False) -> str:
        """Call Anthropic messages API."""
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt or ""},
            ],
        }
        # Anthropic supports structured output via a system instruction.
        if json_mode:
            body["system"] = "Respond ONLY with valid JSON. No prose, no markdown fences."
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get("content") or []
            for block in content_blocks:
                if block.get("type") == "text" and "text" in block:
                    return block["text"]
            # No text blocks at all (e.g. tool-use-only or empty response).
            if content_blocks:
                return content_blocks[0].get("text", "")
            return ""


def load_backend(config: RCABackendConfig) -> RCABackend | None:
    """Factory: instantiate the right backend from config."""
    if not isinstance(config, RCABackendConfig):
        raise TypeError("config must be RCABackendConfig")

    backend_type = config.backend

    if backend_type == "disabled":
        return None
    elif backend_type == "ollama":
        if not config.base_url:
            raise ValueError("TRACEA_RCA_BASE_URL required for ollama backend")
        return OpenAIBackend(
            base_url=config.base_url,
            model=config.model or "llama3",
        )
    elif backend_type == "openai":
        api_key = config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for openai backend")
        return OpenAIBackend(
            model=config.model or "gpt-4o",
            api_key=api_key,
            base_url=config.base_url,
        )
    elif backend_type == "anthropic":
        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for anthropic backend")
        return AnthropicBackend(
            model=config.model or "claude-sonnet-4-20250514",
            api_key=api_key,
            base_url=config.base_url,
        )
    else:
        raise ValueError(f"Unknown RCA backend: {backend_type}")
