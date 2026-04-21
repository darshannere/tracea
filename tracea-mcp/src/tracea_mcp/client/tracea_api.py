"""Client for posting events to the tracea server."""
import asyncio
import os
import httpx
from typing import Optional


class TraceaAPIClient:
    """Posts events to the tracea server."""

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.server_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def post_events(self, events: list[dict]) -> int:
        """Post an event batch to the tracea server. Returns accepted count."""
        client = await self._get_client()
        payload = {"events": events}
        try:
            resp = await client.post("/api/v1/events/mcp", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("accepted", len(events))
        except httpx.HTTPStatusError as e:
            # 4xx = client's problem, don't retry
            if 400 <= e.response.status_code < 500:
                return 0
            raise
        except httpx.RequestError:
            raise

    async def post_events_sync(self, events: list[dict]):
        """Synchronous wrapper for posting events from thread context."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: asyncio.run(self.post_events(events)))


def get_client() -> TraceaAPIClient:
    """Get or create the global TraceaAPIClient from environment."""
    global _client
    if _client is None:
        api_key = os.environ.get("TRACEA_API_KEY", "")
        server_url = os.environ.get("TRACEA_SERVER_URL", "http://localhost:8080")
        _client = TraceaAPIClient(server_url, api_key)
    return _client


_client: Optional[TraceaAPIClient] = None
