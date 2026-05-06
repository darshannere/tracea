"""Brain tool — query the company knowledge base."""
import json
import os

import httpx

from tracea_mcp.tools.base import BaseTool, ToolResult


class BrainTool(BaseTool):
    """Query tracea's Company Brain for relevant knowledge."""

    @property
    def name(self) -> str:
        return "brain"

    @property
    def description(self) -> str:
        return (
            "Query the Company Brain — a synthesized knowledge base built from past "
            "agent sessions. Returns workflows, error fixes, and codebase insights "
            "relevant to your current task. Use this before starting work on a new "
            "task to learn from past agent behavior."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — keywords or a natural language question",
                },
                "category": {
                    "type": "string",
                    "enum": ["workflow", "error_fix", "codebase"],
                    "description": "Optional filter by category",
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        category = args.get("category")

        server_url = os.environ.get("TRACEA_SERVER_URL", "http://localhost:8080").rstrip("/")
        api_key = os.environ.get("TRACEA_API_KEY", "")

        params = {"q": query, "limit": "10"}
        if category:
            params["category"] = category

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{server_url}/api/v1/brain/entries",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Brain API returned {e.response.status_code}: {e.response.text[:200]}",
                exit_code=e.response.status_code,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to query brain: {e}",
                exit_code=1,
            )

        entries = data.get("entries", [])
        if not entries:
            return ToolResult(
                success=True,
                content="No relevant knowledge found in the Company Brain.",
            )

        lines = [f"Found {len(entries)} relevant entr{'y' if len(entries) == 1 else 'ies'}:\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"{i}. [{entry['category'].replace('_', ' ').title()}] {entry['title']}")
            lines.append(f"   Confidence: {entry['confidence'] * 100:.0f}% | Reinforced: {entry['hit_count']} time{'s' if entry['hit_count'] != 1 else ''}")
            lines.append(f"   {entry['content'][:500]}")
            if len(entry['content']) > 500:
                lines.append("   ...")
            lines.append("")

        return ToolResult(success=True, content="\n".join(lines))
