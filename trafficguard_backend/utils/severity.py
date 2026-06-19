"""
utils/severity.py
Per-violation severity normalisation + case severity aggregation.
Case severity = max across all violations (HIGH > MEDIUM > LOW).
"""
from __future__ import annotations

_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_DEFAULT: dict[str, str] = {
    "helmet_non_compliance": "HIGH",
    "seatbelt":              "MEDIUM",
    "triple_riding":         "HIGH",
    "wrong_side":            "HIGH",
    "stop_line":             "LOW",
    "red_light":             "HIGH",
    "illegal_parking":       "LOW",
}


def normalize_severity(violation_type: str, model_severity: str | None) -> str:
    """Return authoritative severity for a violation type.

    Prefer model-provided value if it is a valid enum member,
    otherwise fall back to the hardcoded mapping.
    """
    valid = {"HIGH", "MEDIUM", "LOW"}
    if model_severity and model_severity.upper() in valid:
        return model_severity.upper()
    return _DEFAULT.get(violation_type, "MEDIUM")


def case_severity(violation_severities: list[str]) -> str:
    """Highest severity across all violations in a case."""
    if not violation_severities:
        return "LOW"
    ranked = [_RANK.get(s.upper(), 1) for s in violation_severities]
    max_rank = max(ranked)
    return {3: "HIGH", 2: "MEDIUM", 1: "LOW"}[max_rank]
