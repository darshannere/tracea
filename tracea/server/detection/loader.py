"""RulesLoader — loads and validates detection rules from YAML."""
import os
from pathlib import Path
import ruamel.yaml
from tracea.server.detection.models import Rule, RulesFile

_THRESHOLDS = {
    "cost_usd": float(os.getenv("THRESHOLD_COST", "0.05")),
    "duration_ms": int(os.getenv("THRESHOLD_LATENCY", "30000")),
    "repetition_min_count": int(os.getenv("THRESHOLD_REPEAT", "5")),
}

# Bundled defaults — works in local dev and inside the Docker image (copied to
# /app/defaults by the Dockerfile). Prefer the in-repo path so a fresh clone
# with no data/detection_rules.yaml still loads rules.
_DEFAULTS_DIR_CANDIDATES = [
    Path(__file__).parent / "defaults",            # local dev: tracea/server/detection/defaults/
    Path("/app/defaults"),                          # Docker image
]
_DEFAULT_RULES_FILE = "detection_rules.yaml"


def _find_default_rules() -> Path | None:
    for d in _DEFAULTS_DIR_CANDIDATES:
        p = d / _DEFAULT_RULES_FILE
        if p.exists():
            return p
    return None


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
        """Load rules from YAML file, validate with Pydantic, apply env overrides.

        Falls back to bundled defaults if the configured path does not exist,
        so the server starts cleanly on a fresh clone.
        """
        p = Path(self.path)
        if not p.exists():
            default_path = _find_default_rules()
            if default_path is None:
                print(f"[tracea] No rules file at {self.path} and no bundled defaults found; detection disabled.")
                return []
            print(f"[tracea] No rules file at {self.path}, loading defaults from {default_path}")
            p = default_path

        with open(p) as f:
            data = self._yaml.load(f) or {}

        rules_data = data.get("rules", [])
        # Validate each rule with Pydantic
        validated = [Rule(**rule_dict).model_dump() for rule_dict in rules_data]
        return _apply_env_overrides(validated)

    def validate_rule(self, rule_dict: dict) -> Rule:
        """Validate a single rule dict. Raises ValidationError if invalid."""
        return Rule(**rule_dict)