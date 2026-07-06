"""
Pydantic AI Tool Agent — tracea Observability

A tool-using financial research agent built with pydantic-ai.

tracea's httpx transport patching automatically captures OpenAI LLM calls.
Tool invocations are wrapped with tracea.LogTool for manual instrumentation.

Env vars required: OPENAI_API_KEY, TRACEA_SERVER_URL, TRACEA_API_KEY

Run:
    cp .env.example .env
    pip install -r requirements.txt
    python main.py
"""

import asyncio
import logging
from functools import wraps

from dotenv import find_dotenv, load_dotenv

dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    print("No .env file found.\nUsing process environment variables.")

from pydantic_ai import Agent

import tracea

tracea.init()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def traced_tool(fn):
    """Decorator that wraps a tool function with tracea.LogTool for observability."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        tool_name = fn.__name__
        with tracea.LogTool(tool_name, arguments=kwargs) as lt:
            result = fn(*args, **kwargs)
            lt.result = result
        return result
    return wrapper


agent = Agent(
    "openai-chat:gpt-4o-mini",
    system_prompt=(
        "You are a financial research assistant. "
        "Use available tools to look up stock prices and company information, "
        "then provide a clear, concise analysis."
    ),
)


@agent.tool_plain
@traced_tool
def get_stock_price(symbol: str) -> dict:
    """Get the current stock price for a ticker symbol."""
    stocks = {
        "AAPL": {"price": 178.50, "change": +2.30, "percent": "+1.3%"},
        "GOOGL": {"price": 141.20, "change": -0.80, "percent": "-0.6%"},
        "MSFT": {"price": 378.90, "change": +4.50, "percent": "+1.2%"},
        "NVDA": {"price": 495.20, "change": +12.30, "percent": "+2.5%"},
        "META": {"price": 512.40, "change": +8.10, "percent": "+1.6%"},
    }
    data = stocks.get(symbol.upper(), {"price": 0.0, "change": 0.0, "percent": "N/A"})
    return {"symbol": symbol.upper(), **data}


@agent.tool_plain
@traced_tool
def get_company_info(symbol: str) -> dict:
    """Get basic company information for a ticker symbol."""
    companies = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology", "market_cap": "2.8T"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology", "market_cap": "1.8T"},
        "MSFT": {"name": "Microsoft Corp.", "sector": "Technology", "market_cap": "2.8T"},
        "NVDA": {"name": "NVIDIA Corp.", "sector": "Semiconductors", "market_cap": "1.2T"},
        "META": {"name": "Meta Platforms Inc.", "sector": "Technology", "market_cap": "1.3T"},
    }
    info = companies.get(
        symbol.upper(), {"name": "Unknown", "sector": "Unknown", "market_cap": "N/A"}
    )
    return {"symbol": symbol.upper(), **info}


@agent.tool_plain
@traced_tool
def calculate(expression: str) -> dict:
    """Evaluate a mathematical expression safely."""
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
        result = _eval(ast.parse(expression, mode="eval"))
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


DEMO_QUERIES = [
    "What are the current prices for NVDA and MSFT? Which one has better performance today?",
    "Look up Apple and Google. If I invest $10,000 in each at today's prices, how many shares would I get?",
]


async def run_demo():
    print("=" * 60)
    print("Pydantic AI Tool Agent — Demo (tracea)")
    print("=" * 60)

    for i, query in enumerate(DEMO_QUERIES, 1):
        print(f"\n{'=' * 60}")
        print(f"Query {i}: {query}")
        print("=" * 60)
        result = await agent.run(query)
        print(f"\nAgent: {result.data}\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
    import time
    time.sleep(0.5)
