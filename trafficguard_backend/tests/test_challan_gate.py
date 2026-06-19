"""
tests/test_challan_gate.py

Unit tests for utils/challan.py (auto-challan gate logic).
All fixtures are inline — no external files required.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.challan import evaluate_challan


class TestChallanGate:
    # ── Passing cases ────────────────────────────────────────────────────────

    def test_all_conditions_pass_issues_challan(self):
        issued, status, reason = evaluate_challan(
            max_confidence=0.95,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.92,
        )
        assert issued is True
        assert status == "auto_challan"
        assert reason is None

    def test_confidence_exactly_above_threshold_passes(self):
        """0.93 > 0.92 threshold → should pass."""
        issued, status, _ = evaluate_challan(
            max_confidence=0.93,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.86,
        )
        assert issued is True

    # ── Failing cases ────────────────────────────────────────────────────────

    def test_invalid_plate_blocks_challan(self):
        issued, status, reason = evaluate_challan(
            max_confidence=0.95,
            plate_valid=False,
            case_severity="HIGH",
            camera_trust_score=0.92,
        )
        assert issued is False
        assert status == "pending_review"
        assert "plate" in reason.lower()

    def test_low_confidence_blocks_challan(self):
        issued, status, reason = evaluate_challan(
            max_confidence=0.85,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.92,
        )
        assert issued is False
        assert "confidence" in reason.lower()

    def test_medium_severity_blocks_challan(self):
        issued, status, reason = evaluate_challan(
            max_confidence=0.95,
            plate_valid=True,
            case_severity="MEDIUM",
            camera_trust_score=0.92,
        )
        assert issued is False
        assert "severity" in reason.lower()

    def test_low_trust_score_blocks_challan(self):
        issued, status, reason = evaluate_challan(
            max_confidence=0.95,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.80,
        )
        assert issued is False
        assert "trust" in reason.lower()

    def test_maintenance_camera_zero_trust_blocks(self):
        """Trust score of 0.0 (maintenance camera simulation) must block."""
        issued, status, reason = evaluate_challan(
            max_confidence=0.99,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.0,
        )
        assert issued is False
        assert status == "pending_review"

    def test_multiple_failures_listed_in_reason(self):
        """When several conditions fail, all should appear in the reason string."""
        issued, status, reason = evaluate_challan(
            max_confidence=0.50,
            plate_valid=False,
            case_severity="LOW",
            camera_trust_score=0.30,
        )
        assert issued is False
        assert "confidence" in reason.lower()
        assert "plate" in reason.lower()
        assert "severity" in reason.lower()
        assert "trust" in reason.lower()

    def test_confidence_exactly_at_threshold_fails(self):
        """Confidence <= threshold should NOT pass (strict >)."""
        issued, status, reason = evaluate_challan(
            max_confidence=0.92,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.92,
        )
        assert issued is False
        assert "confidence" in reason.lower()

    def test_trust_score_exactly_at_boundary_fails(self):
        """Trust score <= 0.85 should NOT pass."""
        issued, status, reason = evaluate_challan(
            max_confidence=0.95,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=0.85,
        )
        assert issued is False
        assert "trust" in reason.lower()

    def test_none_trust_score_treated_as_zero(self):
        issued, status, _ = evaluate_challan(
            max_confidence=0.95,
            plate_valid=True,
            case_severity="HIGH",
            camera_trust_score=None,
        )
        assert issued is False
