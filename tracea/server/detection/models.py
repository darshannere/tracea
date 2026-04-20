from pydantic import BaseModel, Field
from typing import Literal, Any


class Condition(BaseModel):
    """A single condition or composite (and/or) condition block."""
    # Simple condition fields
    field: str | None = None
    op: str | None = None
    value: Any = None
    # Composite operators
    and_: list["Condition"] | None = Field(default=None, alias="and")
    or_: list["Condition"] | None = Field(default=None, alias="or")
    # Existence check
    exists: str | None = None

    model_config = {"populate_by_name": True}


class RepetitionBlock(BaseModel):
    """Inline repetition detection block for same-field consecutive count."""
    field: str
    min_count: int = 2


class SessionRule(BaseModel):
    """Count-within-session aggregation rule."""
    count_field: str
    aggregation: Literal["sum", "count", "max", "avg"]
    threshold: float
    op: Literal["gt", "gte", "lt", "lte", "eq"]


class Rule(BaseModel):
    """A complete detection rule with condition, repetition, and session_rules."""
    id: str
    description: str
    condition: Condition
    issue_category: str
    severity: Literal["critical", "high", "medium", "low"]
    repetition: RepetitionBlock | None = None
    session_rules: SessionRule | None = None


class RulesFile(BaseModel):
    """Top-level rules file structure."""
    rules: list[Rule]