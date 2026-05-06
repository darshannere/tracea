"""Pydantic models for brain synthesis."""

from typing import Literal
from pydantic import BaseModel, Field


class BrainEntryExtract(BaseModel):
    """Single brain entry extracted by the LLM."""

    category: Literal["workflow", "error_fix", "codebase"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class BrainSynthesisResult(BaseModel):
    """Top-level result from LLM — a list of extracted entries."""

    entries: list[BrainEntryExtract]
