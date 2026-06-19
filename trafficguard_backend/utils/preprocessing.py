"""
utils/preprocessing.py
Real pixel-level pre-processing using OpenCV.

PDF Differentiator #1 + Demo Moment 1:
  - CLAHE on LAB L-channel for low-light frames
  - fastNlMeansDenoisingColored for blur/rain/fog frames
  - enhance_frame() is independently testable
"""
from __future__ import annotations
import cv2
import numpy as np
from config import LOW_LIGHT_THRESHOLD


def _bytes_to_bgr(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes")
    return img


def _bgr_to_bytes(img: np.ndarray, ext: str = ".jpg") -> bytes:
    success, buf = cv2.imencode(ext, img)
    if not success:
        raise ValueError("Could not encode image")
    return buf.tobytes()


def mean_luminance(image_bytes: bytes) -> float:
    """Return mean pixel luminance (0–255) of the image."""
    img = _bytes_to_bgr(image_bytes)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def apply_clahe(img: np.ndarray) -> np.ndarray:
    """CLAHE on the L-channel of a BGR image (LAB colour space)."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    lab = cv2.merge([l_ch, a_ch, b_ch])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def apply_denoise(img: np.ndarray) -> np.ndarray:
    """Light colour denoising (fast non-local means)."""
    return cv2.fastNlMeansDenoisingColored(img, None, 7, 7, 7, 21)


def enhance_frame(image_bytes: bytes, scene_condition: str | None) -> bytes:
    """
    Apply CLAHE and/or denoise based on detected scene condition.

    Rules
    -----
    - Low light (mean luminance < LOW_LIGHT_THRESHOLD) → always CLAHE
    - scene_condition in {night, blur, rain, fog}       → CLAHE + denoise
    - Otherwise                                         → return unchanged

    Returns enhanced image as JPEG bytes.
    """
    img = _bytes_to_bgr(image_bytes)
    lum = float(np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)))

    degraded_conditions = {"night", "blur", "rain", "fog"}
    low_light = lum < LOW_LIGHT_THRESHOLD
    is_degraded = (scene_condition or "").lower() in degraded_conditions

    if not low_light and not is_degraded:
        return image_bytes          # nothing to do

    if low_light or is_degraded:
        img = apply_clahe(img)      # CLAHE always when degraded

    if is_degraded:
        img = apply_denoise(img)    # extra denoise for blur/rain/fog/night

    return _bgr_to_bytes(img, ".jpg")
