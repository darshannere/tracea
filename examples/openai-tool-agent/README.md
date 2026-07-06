# OpenAI Tool Agent

ReAct-style agent with OpenAI streaming and tool use, instrumented with [tracea](https://github.com/darshannere/tracea).

## Setup

```bash
cp .env.example .env  # fill in your API keys
```

With `uv` (recommended):
```bash
uv run --no-project --python 3.13 --with-requirements requirements.txt python main.py
```

## How it works

tracea automatically captures OpenAI LLM calls via httpx transport patching.
Tool calls are instrumented manually using `tracea.LogTool` and `tracea.log_chat`.

## What it does

Runs two demo queries that exercise tool use:
1. Weather comparison (San Francisco vs Tokyo)
2. Stock price lookup + calculation (NVDA +10%)

Tools: `get_weather`, `get_stock_price`, `calculate`, `get_current_time`
