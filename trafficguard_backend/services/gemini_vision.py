"""
services/gemini_vision.py

Gemini Vision replaces the Claude pipeline — same two-pass strategy,
same JSON output contract, same ALLOWED_TYPES.

Two-pass strategy
-----------------
Pass 1 — raw frame  → get scene_condition
If scene is night/blur/rain/fog OR frame is low-light:
    CLAHE + denoise → Pass 2 on enhanced frame

Model: gemini-1.5-flash  (configurable via GEMINI_VISION_MODEL env var)
"""
from __future__ import annotations
import json
import logging
import os
import random
import re
from typing import Any

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_VISION_MODEL, LOW_LIGHT_THRESHOLD
from utils.preprocessing import enhance_frame, mean_luminance
from utils.severity import normalize_severity

log = logging.getLogger(__name__)

# ── Allowed violation types ────────────────────────────────────────────────
ALLOWED_TYPES = {
    "helmet_non_compliance",
    "seatbelt",
    "triple_riding",
    "wrong_side",
    "stop_line",
    "red_light",
    "illegal_parking",
}

# ── Prompt ────────────────────────────────────────────────────────────────────
PROMPT = """You are a traffic violation detection AI for Bengaluru Traffic Police.
Analyze the provided traffic image and return ONLY valid JSON — no markdown, no prose, no code fences.

Required JSON schema:
{
  "scene_condition": "day" | "night" | "rain" | "fog" | "blur",
  "vehicles": [{"type": string, "count": integer}],
  "violations": [
    {
      "type": one of exactly: helmet_non_compliance | seatbelt | triple_riding | wrong_side | stop_line | red_light | illegal_parking,
      "confidence": float 0.0-1.0,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "description": string (concise, max 120 chars),
      "bounding_hint": string (e.g. "center, motorcycle rider"),
      "signal_state": "red" | "yellow" | "green" | null  (populate ONLY when type == red_light, else null)
    }
  ],
  "license_plate": string | null,
  "plate_confidence": float 0.0-1.0,
  "plate_valid": boolean,
  "summary": string (one sentence, max 200 chars)
}

Rules:
- Return empty violations array [] if no violations are detected.
- Never include violation types not in the allowed list above.
- signal_state MUST be null for every type except red_light.
- All confidence values must be between 0.0 and 1.0.
- Output ONLY the raw JSON object. No other text, no markdown."""


def _get_model() -> genai.GenerativeModel:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/app/apikey "
            "and add it to trafficguard_backend/.env"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_VISION_MODEL)


def _call_gemini(model: genai.GenerativeModel, image_bytes: bytes, pass_label: str) -> dict[str, Any]:
    """Single Gemini vision call — returns parsed dict."""
    log.info("Gemini vision call — pass=%s model=%s", pass_label, GEMINI_VISION_MODEL)

    # Detect image type
    media_type = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"

    response = model.generate_content(
        [
            {"mime_type": media_type, "data": image_bytes},
            PROMPT,
        ],
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,        # low temperature for deterministic JSON
            max_output_tokens=1024,
        ),
    )

    raw_text = response.text.strip()

    # Strip markdown fences if the model still wraps output
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text.strip())

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        log.error("Gemini returned non-JSON (pass=%s): %.300s", pass_label, raw_text)
        raise ValueError(f"Gemini response is not valid JSON: {exc}") from exc


def _clean_violations(raw: list[dict]) -> list[dict]:
    cleaned = []
    for v in raw:
        vtype = v.get("type", "")
        if vtype not in ALLOWED_TYPES:
            log.warning("Gemini returned unknown violation type '%s' — skipping", vtype)
            continue
        signal_state = v.get("signal_state") if vtype == "red_light" else None
        cleaned.append({
            "type": vtype,
            "confidence": max(0.0, min(1.0, float(v.get("confidence", 0.5)))),
            "severity": normalize_severity(vtype, v.get("severity")),
            "description": str(v.get("description", ""))[:200],
            "bounding_hint": str(v.get("bounding_hint", ""))[:200],
            "signal_state": signal_state,
        })
    return cleaned


async def analyze_image(image_bytes: bytes) -> tuple[dict[str, Any], bytes, bytes | None]:
    """
    Analyze a traffic image via Gemini Vision.

    Falls back to a realistic demo response when:
    - GEMINI_API_KEY is missing
    - Quota is exhausted (429)
    - DEMO_MODE=true env var is set

    Returns
    -------
    result         : parsed detection dict
    raw_bytes      : original image bytes
    enhanced_bytes : CLAHE/denoised bytes if a second pass was done, else None
    """
    # ── Demo mode check ──────────────────────────────────────────────────────
    demo_forced = os.getenv("DEMO_MODE", "false").lower() == "true"
    if demo_forced or not GEMINI_API_KEY:
        log.warning("Demo mode active — returning synthetic violation data")
        return _demo_response(image_bytes), image_bytes, None

    # ── Real Gemini path ─────────────────────────────────────────────────────
    try:
        model = _get_model()
        enhanced_bytes: bytes | None = None

        # Pass 1 — raw frame
        result = _call_gemini(model, image_bytes, "pass-1")
        scene  = (result.get("scene_condition") or "").lower()

        # Enhancement check — only do pass-2 if ENABLE_TWO_PASS is set (saves API quota)
        ENABLE_TWO_PASS = os.getenv("ENABLE_TWO_PASS", "false").lower() == "true"
        lum = mean_luminance(image_bytes)
        needs_enhancement = ENABLE_TWO_PASS and (
            scene in {"night", "blur", "rain", "fog"} or lum < LOW_LIGHT_THRESHOLD
        )

        if needs_enhancement:
            log.info("Scene='%s' / lum=%.1f → CLAHE/denoise pass", scene, lum)
            enhanced_bytes = enhance_frame(image_bytes, scene)
            result = _call_gemini(model, enhanced_bytes, "pass-2")

        # Sanitise
        result["violations"]      = _clean_violations(result.get("violations") or [])
        result["vehicles"]        = result.get("vehicles") or []
        result["scene_condition"] = result.get("scene_condition", "day")

        return result, image_bytes, enhanced_bytes

    except Exception as exc:
        err_str = str(exc)
        # On quota exhaustion fall back to demo instead of crashing
        if "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str:
            log.warning("Gemini quota exhausted — falling back to demo mode: %s", err_str[:120])
            return _demo_response(image_bytes), image_bytes, None
        raise


# ── Demo response generator ────────────────────────────────────────────────────
# Produces realistic but synthetic violation data so the UI is fully demonstrable
# without spending any API quota.  Labelled [DEMO] in the summary.
_DEMO_SCENARIOS = [
    {
        "scene_condition": "day",
        "vehicles": [{"type": "motorcycle", "count": 1}],
        "violations": [
            {
                "type": "helmet_non_compliance",
                "confidence": 0.94,
                "severity": "HIGH",
                "description": "Rider not wearing a helmet [DEMO]",
                "bounding_hint": "center, motorcycle rider",
                "signal_state": None,
            }
        ],
        "license_plate": "KA03MX4521",
        "plate_confidence": 0.91,
        "plate_valid": True,
        "summary": "[DEMO] Motorcyclist without helmet detected at Silk Board Junction.",
    },
    {
        "scene_condition": "day",
        "vehicles": [{"type": "motorcycle", "count": 1}],
        "violations": [
            {
                "type": "triple_riding",
                "confidence": 0.89,
                "severity": "HIGH",
                "description": "Three persons on two-wheeler [DEMO]",
                "bounding_hint": "center-left, motorcycle",
                "signal_state": None,
            }
        ],
        "license_plate": "MH04AB1234",
        "plate_confidence": 0.88,
        "plate_valid": True,
        "summary": "[DEMO] Triple riding violation detected — three occupants on a two-wheeler.",
    },
    {
        "scene_condition": "night",
        "vehicles": [{"type": "car", "count": 1}],
        "violations": [
            {
                "type": "red_light",
                "confidence": 0.96,
                "severity": "HIGH",
                "description": "Vehicle crossed red signal [DEMO]",
                "bounding_hint": "center, car at intersection",
                "signal_state": "red",
            }
        ],
        "license_plate": "KA01AB5678",
        "plate_confidence": 0.93,
        "plate_valid": True,
        "summary": "[DEMO] Red light violation detected at night — vehicle crossed active red signal.",
    },
    {
        "scene_condition": "day",
        "vehicles": [{"type": "car", "count": 1}],
        "violations": [
            {
                "type": "seatbelt",
                "confidence": 0.87,
                "severity": "MEDIUM",
                "description": "Driver not wearing seatbelt [DEMO]",
                "bounding_hint": "center, car driver seat",
                "signal_state": None,
            }
        ],
        "license_plate": "TN22CC5678",
        "plate_confidence": 0.85,
        "plate_valid": True,
        "summary": "[DEMO] Driver operating vehicle without seatbelt on Hosur Road.",
    },
    {
        "scene_condition": "day",
        "vehicles": [],
        "violations": [],
        "license_plate": None,
        "plate_confidence": 0.0,
        "plate_valid": False,
        "summary": "[DEMO] No traffic violations detected in this frame.",
    },
]


def _demo_response(image_bytes: bytes) -> dict[str, Any]:
    """
    Pick a demo scenario deterministically based on image size
    so the same image always returns the same scenario, but
    different images get different results.
    """
    # Use image size mod to pick scenario (gives variety without randomness)
    idx = len(image_bytes) % (len(_DEMO_SCENARIOS) - 1)  # exclude no-violation for most
    scenario = _DEMO_SCENARIOS[idx].copy()
    scenario["violations"] = _clean_violations(scenario.get("violations") or [])
    scenario["vehicles"]   = scenario.get("vehicles") or []
    log.info("Demo response: scenario=%d violations=%d", idx, len(scenario["violations"]))
    return scenario
