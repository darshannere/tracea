"""Condition evaluation engine for detection rules."""
from tracea.server.detection.models import Condition

OPERATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: (a is not None and b is not None) and float(a) > float(b),
    "gte": lambda a, b: (a is not None and b is not None) and float(a) >= float(b),
    "lt": lambda a, b: (a is not None and b is not None) and float(a) < float(b),
    "lte": lambda a, b: (a is not None and b is not None) and float(a) <= float(b),
    "equals": lambda a, b: str(a) == str(b),
    "contains": lambda a, b: str(b) in str(a) if a is not None else False,
    "starts_with": lambda a, b: str(a).startswith(str(b)) if a is not None else False,
    "exists": lambda a, _: a is not None and a != "",
}


def evaluate_condition(condition: dict, event: dict) -> bool:
    """Evaluate a condition dict against an event dict.

    Supports:
    - Simple conditions: {field, op, value}
    - Existence checks: {exists: field_name}
    - Composite AND: {and: [conditions]}
    - Composite OR: {or: [conditions]}
    """
    # Handle composite AND
    if "and" in condition:
        return all(evaluate_condition(c, event) for c in condition["and"])

    # Handle composite OR
    if "or" in condition:
        return any(evaluate_condition(c, event) for c in condition["or"])

    # Handle existence check
    if "exists" in condition:
        field = condition["exists"]
        val = event.get(field)
        return val is not None and val != ""

    # Handle simple condition
    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")

    if not field or not op:
        return False

    event_val = event.get(field)
    op_fn = OPERATORS.get(op)
    if not op_fn:
        return False

    return op_fn(event_val, value)


def check_repetition(event: dict, recent_events: list[dict], rep_field: str, min_count: int) -> bool:
    """Check if current event continues a repetition streak.

    Args:
        event: Current event dict
        recent_events: List of recent events (chronological order, oldest first)
        rep_field: Field name to check for repetition
        min_count: Minimum consecutive occurrences required

    Returns:
        True if the current event's rep_field value matches the last min_count-1 events
    """
    current_value = event.get(rep_field)
    if current_value is None:
        return False

    # Not enough events to meet min_count (need min_count-1 previous events, current counts as 1)
    if len(recent_events) < min_count - 1:
        return False

    count = 1
    # Check recent events in reverse (most recent first)
    for prev in reversed(recent_events[-min_count + 1:]):
        if prev.get(rep_field) == current_value:
            count += 1
        else:
            break

    return count >= min_count