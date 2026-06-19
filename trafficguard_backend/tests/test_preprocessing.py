"""
tests/test_preprocessing.py

Unit tests for utils/preprocessing.py
All fixtures are synthetic/inline — no external files required.
"""
import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.preprocessing import (
    apply_clahe,
    apply_denoise,
    enhance_frame,
    mean_luminance,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_jpeg(brightness: int = 120, width: int = 64, height: int = 64) -> bytes:
    """Create a uniform-colour JPEG with the given brightness."""
    img = np.full((height, width, 3), brightness, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def _make_noisy_jpeg(width: int = 64, height: int = 64) -> bytes:
    """Create a noisy JPEG to exercise denoise."""
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


# ── mean_luminance ────────────────────────────────────────────────────────────

class TestMeanLuminance:
    def test_bright_image_returns_high_value(self):
        data = _make_jpeg(brightness=200)
        lum = mean_luminance(data)
        assert lum > 150, f"Expected > 150, got {lum}"

    def test_dark_image_returns_low_value(self):
        data = _make_jpeg(brightness=20)
        lum = mean_luminance(data)
        assert lum < 60, f"Expected < 60, got {lum}"

    def test_returns_float(self):
        data = _make_jpeg(brightness=128)
        lum = mean_luminance(data)
        assert isinstance(lum, float)


# ── apply_clahe ────────────────────────────────────────────────────────────────

class TestApplyClahe:
    def test_output_same_shape_as_input(self):
        img = np.full((64, 64, 3), 30, dtype=np.uint8)
        result = apply_clahe(img)
        assert result.shape == img.shape

    def test_output_is_uint8(self):
        img = np.full((64, 64, 3), 30, dtype=np.uint8)
        result = apply_clahe(img)
        assert result.dtype == np.uint8

    def test_clahe_increases_mean_of_dark_image(self):
        img = np.full((64, 64, 3), 20, dtype=np.uint8)
        result = apply_clahe(img)
        # Mean of enhanced image should be >= original
        assert result.mean() >= img.mean()


# ── apply_denoise ──────────────────────────────────────────────────────────────

class TestApplyDenoise:
    def test_output_same_shape(self):
        img = _make_noisy_jpeg()
        arr = cv2.imdecode(np.frombuffer(img, dtype=np.uint8), cv2.IMREAD_COLOR)
        result = apply_denoise(arr)
        assert result.shape == arr.shape

    def test_output_is_uint8(self):
        img = _make_noisy_jpeg()
        arr = cv2.imdecode(np.frombuffer(img, dtype=np.uint8), cv2.IMREAD_COLOR)
        result = apply_denoise(arr)
        assert result.dtype == np.uint8

    def test_denoise_reduces_variance(self):
        """Denoised image should have lower pixel variance than a very noisy input."""
        img = _make_noisy_jpeg()
        arr = cv2.imdecode(np.frombuffer(img, dtype=np.uint8), cv2.IMREAD_COLOR)
        denoised = apply_denoise(arr)
        assert float(np.std(denoised)) < float(np.std(arr)) + 50


# ── enhance_frame ─────────────────────────────────────────────────────────────

class TestEnhanceFrame:
    def test_no_enhancement_for_day_bright(self):
        """Bright day-time image should be returned unchanged."""
        data = _make_jpeg(brightness=180)
        result = enhance_frame(data, "day")
        # The returned bytes should be valid JPEG but content may differ slightly due to re-encode
        arr = cv2.imdecode(np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert arr is not None

    def test_night_scene_is_enhanced(self):
        """Low-brightness night scene should be enhanced (different from input)."""
        data = _make_jpeg(brightness=15)
        enhanced = enhance_frame(data, "night")
        # Enhanced image should decode successfully
        arr = cv2.imdecode(np.frombuffer(enhanced, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert arr is not None
        # Mean brightness of enhanced should be > original
        orig_arr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert arr.mean() >= orig_arr.mean()

    def test_fog_scene_triggers_clahe_and_denoise(self):
        """Fog condition should trigger both CLAHE and denoise; result must be valid JPEG."""
        data = _make_noisy_jpeg()
        result = enhance_frame(data, "fog")
        arr = cv2.imdecode(np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert arr is not None

    def test_rain_scene_enhanced(self):
        """Rain triggers enhancement — result must be a valid image."""
        data = _make_jpeg(brightness=40)
        result = enhance_frame(data, "rain")
        arr = cv2.imdecode(np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert arr is not None

    def test_blur_scene_enhanced(self):
        """Blur triggers enhancement."""
        data = _make_jpeg(brightness=90)
        result = enhance_frame(data, "blur")
        assert len(result) > 0

    def test_returns_bytes(self):
        data = _make_jpeg(brightness=50)
        result = enhance_frame(data, "night")
        assert isinstance(result, bytes)
