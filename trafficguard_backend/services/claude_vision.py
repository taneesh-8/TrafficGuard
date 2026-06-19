"""
services/claude_vision.py

One Claude vision API call replaces the YOLO + OCR + scene-classifier pipeline.

Two-pass strategy
-----------------
Pass 1 — raw frame → get scene_condition
If scene_condition in {night, blur, rain, fog} OR low-light detected:
    enhance frame (CLAHE / denoise) then
Pass 2 — enhanced frame → get full violation analysis

Model: claude-opus-4-7  (configurable via CLAUDE_VISION_MODEL env var)
"""
from __future__ import annotations
import base64
import json
import logging
import re
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_VISION_MODEL
from utils.preprocessing import enhance_frame, mean_luminance
from utils.severity import normalize_severity
from config import LOW_LIGHT_THRESHOLD

log = logging.getLogger(__name__)

# ── Allowed violation types (spec) ────────────────────────────────────────
ALLOWED_TYPES = {
    "helmet_non_compliance",
    "seatbelt",
    "triple_riding",
    "wrong_side",
    "stop_line",
    "red_light",
    "illegal_parking",
}

# ── System prompt ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a traffic violation detection AI for Bengaluru Traffic Police.
Analyze the provided traffic image and return ONLY valid JSON — no markdown, no prose, no code fences.

Required JSON schema:
{
  "scene_condition": "day"|"night"|"rain"|"fog"|"blur",
  "vehicles": [{"type": string, "count": integer}],
  "violations": [
    {
      "type": one of exactly: helmet_non_compliance|seatbelt|triple_riding|wrong_side|stop_line|red_light|illegal_parking,
      "confidence": float 0.0-1.0,
      "severity": "HIGH"|"MEDIUM"|"LOW",
      "description": string (concise, ≤120 chars),
      "bounding_hint": string (e.g. "center, motorcycle rider"),
      "signal_state": "red"|"yellow"|"green"|null  (only populate when type == red_light, else always null)
    }
  ],
  "license_plate": string|null,
  "plate_confidence": float 0.0-1.0,
  "plate_valid": boolean,
  "summary": string (one sentence, ≤200 chars)
}

Rules:
- Return empty violations array [] if no violations are detected.
- Never include violation types not in the allowed list.
- signal_state MUST be null for every violation type except red_light.
- All confidence values must be between 0.0 and 1.0.
- Output ONLY the JSON object. No other text whatsoever."""


def _get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Set it in your .env file or environment. "
            "/analyze cannot function without it."
        )
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _image_to_b64(image_bytes: bytes) -> tuple[str, str]:
    """Return (base64_data, media_type) for the image."""
    # Detect JPEG vs PNG by magic bytes
    media_type = "image/jpeg"
    if image_bytes[:4] == b"\x89PNG":
        media_type = "image/png"
    return base64.standard_b64encode(image_bytes).decode(), media_type


def _call_claude(client: anthropic.Anthropic, image_bytes: bytes, pass_label: str) -> dict[str, Any]:
    """Make a single vision API call and parse the JSON response."""
    b64, media_type = _image_to_b64(image_bytes)
    log.info("Claude vision call — pass=%s model=%s", pass_label, CLAUDE_VISION_MODEL)

    message = client.messages.create(
        model=CLAUDE_VISION_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analyze this traffic camera frame for violations. "
                            "Return only JSON as specified."
                        ),
                    },
                ],
            }
        ],
    )

    raw_text = message.content[0].text.strip()

    # Strip accidental markdown fences the model might still include
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text.strip())

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        log.error("Claude returned non-JSON (pass=%s): %s", pass_label, raw_text[:300])
        raise ValueError(f"Claude response is not valid JSON: {exc}") from exc


def _clean_violations(raw_violations: list[dict]) -> list[dict]:
    """Filter to allowed types and normalise severity."""
    cleaned = []
    for v in raw_violations:
        vtype = v.get("type", "")
        if vtype not in ALLOWED_TYPES:
            log.warning("Claude returned unknown violation type '%s' — skipping", vtype)
            continue
        # signal_state only valid for red_light
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
    Analyze a traffic image via Claude Vision.

    Returns
    -------
    result          : parsed detection dict
    raw_bytes       : original image bytes (unchanged)
    enhanced_bytes  : enhanced bytes if a second pass was made, else None
    """
    client = _get_client()
    enhanced_bytes: bytes | None = None

    # Pass 1 — raw frame
    result = _call_claude(client, image_bytes, "pass-1")
    scene = (result.get("scene_condition") or "").lower()

    # Decide if enhancement is warranted
    lum = mean_luminance(image_bytes)
    needs_enhancement = scene in {"night", "blur", "rain", "fog"} or lum < LOW_LIGHT_THRESHOLD

    if needs_enhancement:
        log.info(
            "Scene condition '%s' / luminance %.1f → applying CLAHE/denoise and re-analysing",
            scene, lum,
        )
        enhanced_bytes = enhance_frame(image_bytes, scene)
        # Pass 2 — enhanced frame
        result = _call_claude(client, enhanced_bytes, "pass-2")

    # Sanitise output
    result["violations"] = _clean_violations(result.get("violations") or [])
    result["vehicles"] = result.get("vehicles") or []
    result["scene_condition"] = result.get("scene_condition", "day")

    return result, image_bytes, enhanced_bytes
