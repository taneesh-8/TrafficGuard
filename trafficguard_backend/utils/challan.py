"""
utils/challan.py
Auto-challan gate — all four conditions must pass.

Conditions
----------
1. confidence > AUTO_CHALLAN_CONFIDENCE_THRESHOLD  (per-violation max)
2. plate_valid = True
3. case severity = HIGH
4. camera trust_score > 0.85

Returns (challan_issued: bool, status: str, review_reason: str | None)
"""
from __future__ import annotations
from config import AUTO_CHALLAN_CONFIDENCE_THRESHOLD


def evaluate_challan(
    max_confidence: float,
    plate_valid: bool,
    case_severity: str,
    camera_trust_score: float | None,
) -> tuple[bool, str, str | None]:
    """
    Returns
    -------
    challan_issued : bool
    status         : "auto_challan" | "pending_review" | "no_violation"
    review_reason  : human-readable string listing failed conditions, or None
    """
    failed: list[str] = []

    if max_confidence <= AUTO_CHALLAN_CONFIDENCE_THRESHOLD:
        failed.append(
            f"confidence {max_confidence:.2f} ≤ threshold {AUTO_CHALLAN_CONFIDENCE_THRESHOLD}"
        )
    if not plate_valid:
        failed.append("plate not validated")
    if case_severity != "HIGH":
        failed.append(f"case severity is {case_severity} (requires HIGH)")
    trust = camera_trust_score if camera_trust_score is not None else 0.0
    if trust <= 0.85:
        failed.append(f"camera trust score {trust:.2f} ≤ 0.85")

    if failed:
        return False, "pending_review", "Auto-challan blocked: " + "; ".join(failed)
    return True, "auto_challan", None
