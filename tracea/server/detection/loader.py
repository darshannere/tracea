"""RulesLoader — loads and validates detection rules from YAML."""
import os
import ruamel.yaml
from tracea.server.detection.models import Rule, RulesFile

_THRESHOLDS = {
    "cost_usd": float(os.getenv("THRESHOLD_COST", "0.05")),
    "duration_ms": int(os.getenv("THRESHOLD_LATENCY", "30000")),
    "repetition_min_count": int(os.getenv("THRESHOLD_REPEAT", "5")),
}


def _apply_env_overrides(rules: list[dict]) -> list[dict]:
    """Pre-process rules: apply env var threshold overrides."""
    for rule in rules:
        rule_id = rule.get("id", "")
        if rule_id == "high_cost" and "condition" in rule and "value" in rule["condition"]:
            rule["condition"]["value"] = _THRESHOLDS["cost_usd"]
        elif rule_id == "high_latency" and "condition" in rule and "value" in rule["condition"]:
            rule["condition"]["value"] = _THRESHOLDS["duration_ms"]
        elif rule_id == "repeated_tool_call" and "repetition" in rule:
            rule["repetition"]["min_count"] = _THRESHOLDS["repetition_min_count"]
        elif rule_id == "infinite_loop" and "repetition" in rule:
            rule["repetition"]["min_count"] = _THRESHOLDS["repetition_min_count"] * 2
    return rules


class RulesLoader:
    """Loads and validates detection rules from YAML. Uses ruamel.yaml (never yaml.load)."""

    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("TRACEA_RULES_PATH", "./data/detection_rules.yaml")
        self._yaml = ruamel.yaml.YAML()
        self._yaml.preserve_quotes = True

    def load(self) -> list[dict]:
        """Load rules from YAML file, validate with Pydantic, apply env overrides."""
        try:
            with open(self.path) as f:
                data = self._yaml.load(f) or {}
        except FileNotFoundError:
            default_path = "/app/defaults/detection_rules.yaml"
            print(f"[tracea] No rules file at {self.path}, loading defaults from {default_path}")
            with open(default_path) as f:
                data = self._yaml.load(f) or {}

        rules_data = data.get("rules", [])
        # Validate each rule with Pydantic
        validated = [Rule(**rule_dict).model_dump() for rule_dict in rules_data]
        return _apply_env_overrides(validated)

    def validate_rule(self, rule_dict: dict) -> Rule:
        """Validate a single rule dict. Raises ValidationError if invalid."""
        return Rule(**rule_dict)