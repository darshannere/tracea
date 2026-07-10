"""
OpenAI ReAct agent with tool use and tracea observability.

tracea auto-captures OpenAI LLM calls via httpx transport patching.
Tool calls are instrumented manually using tracea.LogTool and tracea.log_chat.

Usage:
    cp .env.example .env
    pip install -r requirements.txt
    python main.py
"""

import asyncio
import json
import logging
from datetime import datetime
from types import SimpleNamespace

from dotenv import find_dotenv, load_dotenv

dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    print("No .env file found.\nUsing process environment variables.")

import openai

import tracea

tracea.init()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TOOLS = {}


def register_tool(name=None):
    def decorator(fn):
        tool_name = name or fn.__name__
        TOOLS[tool_name] = fn
        return fn
    return decorator


@register_tool()
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    weather_db = {
        "san francisco": {"temp": 68, "condition": "foggy", "humidity": 75},
        "new york": {"temp": 45, "condition": "cloudy", "humidity": 60},
        "london": {"temp": 52, "condition": "rainy", "humidity": 85},
        "tokyo": {"temp": 72, "condition": "sunny", "humidity": 50},
    }
    data = weather_db.get(city.lower(), {"temp": 70, "condition": "unknown", "humidity": 50})
    return {"city": city, **data}


@register_tool()
def get_stock_price(symbol: str) -> dict:
    """Get stock price for a symbol."""
    stocks = {
        "AAPL": {"price": 178.50, "change": +2.30, "percent": "+1.3%"},
        "GOOGL": {"price": 141.20, "change": -0.80, "percent": "-0.6%"},
        "MSFT": {"price": 378.90, "change": +4.50, "percent": "+1.2%"},
        "NVDA": {"price": 495.20, "change": +12.30, "percent": "+2.5%"},
    }
    data = stocks.get(symbol.upper(), {"price": 0, "change": 0, "percent": "N/A"})
    return {"symbol": symbol.upper(), **data}


@register_tool()
def calculate(expression: str) -> dict:
    """Evaluate a math expression safely using AST parsing."""
    import ast
    import operator

    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


@register_tool()
def get_current_time(timezone: str = "UTC") -> dict:
    """Get current time."""
    return {"timezone": timezone, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get current stock price for a ticker symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression (e.g., '2 + 2 * 3')",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "Timezone (default: UTC)"}
                },
            },
        },
    },
]


class ReActAgent:
    """ReAct-style agent that reasons and acts in a loop with streaming."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = openai.OpenAI()
        self.model = model
        self.messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful AI assistant with access to tools. "
                    "Use available tools to gather information, then provide "
                    "a clear, comprehensive answer."
                ),
            }
        ]

    def _execute_tool(self, name: str, arguments: dict) -> str:
        if name not in TOOLS:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = TOOLS[name](**arguments)
            tracea.log_chat(
                role="assistant",
                content=f"Tool result: {json.dumps(result)}",
                model=self.model,
                provider="openai",
            )
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _stream_completion(self) -> SimpleNamespace:
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            stream=True,
            stream_options={"include_usage": True},
        )

        content = ""
        tool_calls: dict[int, dict] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content += delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls[idx]["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += tc.function.arguments

        return SimpleNamespace(
            content=content,
            tool_calls=[
                SimpleNamespace(
                    id=tc["id"],
                    function=SimpleNamespace(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in tool_calls.values()
            ]
            or None,
        )

    def run(self, query: str) -> str:
        self.messages.append({"role": "user", "content": query})

        for _ in range(5):
            msg = self._stream_completion()

            if not msg.tool_calls:
                self.messages.append({"role": "assistant", "content": msg.content})
                return msg.content

            self.messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )

            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                logger.info(f"Tool call: {tc.function.name}({args})")
                with tracea.LogTool(tc.function.name, arguments=args, tool_call_id=tc.id) as lt:
                    result = self._execute_tool(tc.function.name, args)
                    lt.result = result
                logger.info(f"Tool result: {result}")
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return "I wasn't able to complete this task within the allowed steps."


DEMO_QUERIES = [
    "What's the weather in San Francisco and Tokyo? Compare them.",
    "What's NVDA stock price? If it goes up 10%, what would the new price be?",
]


def run_demo():
    for i, query in enumerate(DEMO_QUERIES, 1):
        agent = ReActAgent()
        print(f"\n{'=' * 60}")
        print(f"Query {i}: {query}")
        print("=" * 60)
        result = agent.run(query)
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    run_demo()
    from tracea.patch.httpx import drain_queue
    drain_queue(timeout=2.0)
    import time
    time.sleep(1.0)
