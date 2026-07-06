# Pydantic AI Tool Agent

A tool-using financial research agent built with [pydantic-ai](https://ai.pydantic.dev), instrumented with [tracea](https://github.com/darshannere/tracea).

## Setup

```bash
cp .env.example .env  # fill in your API keys
```

With `uv` (recommended):
```bash
uv run --no-project --python 3.13 --with-requirements requirements.txt python main.py
```

## How it works

tracea automatically captures pydantic-ai's OpenAI LLM calls via httpx transport patching.
Tool invocations are captured by wrapping `@agent.tool_plain` functions with `tracea.LogTool`.

## What it does

Runs two demo queries that exercise tool use:
1. Compare NVDA and MSFT stock prices and performance
2. Calculate share counts for Apple and Google at current prices

Tools: `get_stock_price`, `get_company_info`, `calculate`
