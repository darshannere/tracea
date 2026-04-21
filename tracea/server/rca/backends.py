"""RCA backends: disabled, ollama, openai, anthropic."""
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from tracea.server.rca.models import RCAContext, RCABackendConfig


class RCABackend(ABC):
    """Abstract RCA backend. All methods are async."""

    @abstractmethod
    async def analyze(self, context: RCAContext, prompt: str | None = None) -> str:
        """Returns RCA text content, or raises on failure."""
        ...


class DisabledBackend(RCABackend):
    """No-op backend. Always returns empty string."""

    async def analyze(self, context: RCAContext, prompt: str | None = None) -> str:
        return ""


class OllamaBackend(RCABackend):
    """Ollama backend via OpenAI-compatible API."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model or "llama3"

    async def analyze(self, context: RCAContext, prompt: str | None = None) -> str:
        """Call Ollama via OpenAI-compatible chat completions endpoint."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a DevOps root-cause analyst."},
                        {"role": "user", "content": prompt or ""},
                    ],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class OpenAIBackend(RCABackend):
    """OpenAI cloud backend."""

    def __init__(self, model: str, api_key: str):
        self.model = model or "gpt-4o"
        self.api_key = api_key

    async def analyze(self, context: RCAContext, prompt: str | None = None) -> str:
        """Call OpenAI chat completions API."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a DevOps root-cause analyst."},
                        {"role": "user", "content": prompt or ""},
                    ],
                    "stream": False,
                },
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

    async def analyze(self, context: RCAContext, prompt: str | None = None) -> str:
        """Call Anthropic messages API."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 512,
                    "messages": [
                        {"role": "user", "content": prompt or ""},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            # Anthropic-compatible APIs may return thinking blocks before text blocks
            for block in data.get("content", []):
                if block.get("type") == "text" and "text" in block:
                    return block["text"]
            # Fallback to first content block
            return data["content"][0].get("text", "")


def load_backend(config: RCABackendConfig) -> RCABackend:
    """Factory: instantiate the right backend from config."""
    if not isinstance(config, RCABackendConfig):
        raise TypeError("config must be RCABackendConfig")

    backend_type = config.backend

    if backend_type == "disabled":
        return DisabledBackend()
    elif backend_type == "ollama":
        if not config.base_url:
            raise ValueError("TRACEA_RCA_BASE_URL required for ollama backend")
        return OllamaBackend(
            base_url=config.base_url,
            model=config.model or "llama3",
        )
    elif backend_type == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY env var required for openai backend")
        return OpenAIBackend(
            model=config.model or "gpt-4o",
            api_key=api_key,
        )
    elif backend_type == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY env var required for anthropic backend")
        return AnthropicBackend(
            model=config.model or "claude-sonnet-4-20250514",
            api_key=api_key,
            base_url=config.base_url,
        )
    else:
        raise ValueError(f"Unknown RCA backend: {backend_type}")
