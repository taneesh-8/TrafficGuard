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

    Returns
    -------
    result         : parsed detection dict
    raw_bytes      : original image bytes
    enhanced_bytes : CLAHE/denoised bytes if a second pass was done, else None
    """
    model = _get_model()
    enhanced_bytes: bytes | None = None

    # Pass 1 — raw frame
    result = _call_gemini(model, image_bytes, "pass-1")
    scene  = (result.get("scene_condition") or "").lower()

    # Enhancement check
    lum = mean_luminance(image_bytes)
    needs_enhancement = scene in {"night", "blur", "rain", "fog"} or lum < LOW_LIGHT_THRESHOLD

    if needs_enhancement:
        log.info("Scene='%s' / lum=%.1f → CLAHE/denoise pass", scene, lum)
        enhanced_bytes = enhance_frame(image_bytes, scene)
        result = _call_gemini(model, enhanced_bytes, "pass-2")

    # Sanitise
    result["violations"]     = _clean_violations(result.get("violations") or [])
    result["vehicles"]       = result.get("vehicles") or []
    result["scene_condition"] = result.get("scene_condition", "day")

    return result, image_bytes, enhanced_bytes
