# Contributing to tracea

Thanks for your interest in contributing! This document covers how to get started.

## Development Setup

### Backend

```bash
# Install with uv (recommended) or pip
uv pip install -e "."

# Or
pip install -e "."
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
```

### SDK

```bash
cd sdk-python
uv pip install -e "."
```

### MCP Server

```bash
cd tracea-mcp
uv pip install -e "."
```

## Running Tests

```bash
# Backend tests
pytest tests/

# SDK tests
cd sdk-python && pytest

# MCP tests
cd tracea-mcp && pytest
```

## Code Style

- Python: follow PEP 8, use type hints where practical
- TypeScript/React: follow the existing patterns in `dashboard/src/`
- Keep changes focused — one logical change per PR

## Pull Request Process

1. Fork the repo and create a branch
2. Make your changes with clear commit messages
3. Add tests if you're changing behavior
4. Update README/docs if needed
5. Open a PR with a description of what changed and why

## Reporting Issues

Please include:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (Python version, OS, etc.)

## Questions?

Open a [Discussion](https://github.com/darshannere/tracea/discussions) or ping us in an issue.
