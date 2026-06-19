"""
generate_eval_set.py

Creates a small SYNTHETIC labeled test set entirely within this project.
No external dataset, no downloads, no external images.

The "images" are OpenCV-drawn synthetic scenes:
  - Coloured rectangles standing in for vehicles
  - Text overlays standing in for license plates / helmets
  - Deliberately varied lighting (brightness adjustment) to exercise preprocessing

Output structure:
    eval_set/
        images/
            sample_00.jpg  ...
        ground_truth.json  ← list of {filename, violations[], plate, severity}

Usage:
    python generate_eval_set.py [--out-dir eval_set]

NOTE: These are intentionally NOT real traffic images.
      Real accuracy benchmarks should come from photos you supply yourself.
"""
from __future__ import annotations
import argparse
import json
import os
import random
from pathlib import Path

import cv2
import numpy as np


SYNTHETIC_SAMPLES = [
    # (description, violations, plate, severity, brightness_factor)
    {
        "id": "sample_00",
        "violations": [{"type": "helmet_non_compliance", "confidence": 0.95, "severity": "HIGH",
                        "description": "Rider without helmet", "bounding_hint": "center", "signal_state": None}],
        "plate": "KA03MX4521",
        "severity": "HIGH",
        "brightness": 1.0,
    },
    {
        "id": "sample_01",
        "violations": [{"type": "red_light", "confidence": 0.93, "severity": "HIGH",
                        "description": "Vehicle crossing red signal", "bounding_hint": "left", "signal_state": "red"}],
        "plate": "MH04AB1234",
        "severity": "HIGH",
        "brightness": 0.9,
    },
    {
        "id": "sample_02",
        "violations": [{"type": "triple_riding", "confidence": 0.88, "severity": "HIGH",
                        "description": "Three riders on two-wheeler", "bounding_hint": "right", "signal_state": None}],
        "plate": "KA51MG9901",
        "severity": "HIGH",
        "brightness": 0.3,   # low-light → exercises CLAHE
    },
    {
        "id": "sample_03",
        "violations": [{"type": "illegal_parking", "confidence": 0.75, "severity": "LOW",
                        "description": "Vehicle parked in no-parking zone", "bounding_hint": "bottom-left", "signal_state": None}],
        "plate": "DL01AB9999",
        "severity": "LOW",
        "brightness": 1.0,
    },
    {
        "id": "sample_04",
        "violations": [{"type": "seatbelt", "confidence": 0.82, "severity": "MEDIUM",
                        "description": "Driver not wearing seatbelt", "bounding_hint": "center, car driver", "signal_state": None}],
        "plate": "TN22CC5678",
        "severity": "MEDIUM",
        "brightness": 0.8,
    },
    {
        "id": "sample_05",
        "violations": [],
        "plate": "KA19PA0001",
        "severity": "LOW",
        "brightness": 1.0,
    },
    {
        "id": "sample_06",
        "violations": [{"type": "wrong_side", "confidence": 0.91, "severity": "HIGH",
                        "description": "Vehicle driving on wrong side of road", "bounding_hint": "top-center", "signal_state": None}],
        "plate": "KA05MR8829",
        "severity": "HIGH",
        "brightness": 0.5,   # moderate low light
    },
    {
        "id": "sample_07",
        "violations": [{"type": "stop_line", "confidence": 0.70, "severity": "LOW",
                        "description": "Crossed stop line at intersection", "bounding_hint": "bottom-right", "signal_state": None}],
        "plate": "GJ01AA1111",
        "severity": "LOW",
        "brightness": 0.95,
    },
]


def _draw_synthetic_scene(sample: dict) -> np.ndarray:
    """Draw a simple synthetic traffic scene using OpenCV primitives."""
    rng = random.Random(hash(sample["id"]))
    img = np.ones((480, 640, 3), dtype=np.uint8) * 80    # dark grey background

    # Road
    cv2.rectangle(img, (0, 240), (640, 480), (60, 60, 60), -1)
    cv2.line(img, (320, 240), (320, 480), (255, 255, 0), 2)   # centre line

    # Sky
    cv2.rectangle(img, (0, 0), (640, 240), (120, 160, 200), -1)

    # Vehicle rectangle
    vx = rng.randint(100, 400)
    vy = rng.randint(260, 360)
    vcolor = (rng.randint(100, 220), rng.randint(100, 220), rng.randint(100, 220))
    cv2.rectangle(img, (vx, vy), (vx + 120, vy + 80), vcolor, -1)
    cv2.rectangle(img, (vx, vy), (vx + 120, vy + 80), (0, 0, 0), 2)   # outline

    # "Helmet" or lack thereof indicator
    violations = sample.get("violations", [])
    vtypes = {v["type"] for v in violations}
    helmet_color = (0, 255, 0) if "helmet_non_compliance" not in vtypes else (0, 0, 255)
    cv2.circle(img, (vx + 30, vy - 15), 12, helmet_color, -1)

    # Traffic signal (only for red_light)
    if "red_light" in vtypes:
        cv2.rectangle(img, (580, 100), (620, 200), (30, 30, 30), -1)
        for i, col in enumerate([(0, 0, 200), (0, 165, 255), (0, 200, 0)]):
            cv2.circle(img, (600, 120 + i * 30), 10, col, -1)
        # Red light on
        cv2.circle(img, (600, 120), 10, (0, 0, 255), -1)

    # License plate
    plate = sample.get("plate", "")
    plate_clean = plate.replace(" ", "")
    cv2.rectangle(img, (vx + 30, vy + 60), (vx + 110, vy + 78), (255, 255, 255), -1)
    cv2.putText(img, plate_clean[:10], (vx + 33, vy + 74),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1, cv2.LINE_AA)

    # Brightness adjustment
    bf = sample.get("brightness", 1.0)
    img = np.clip(img.astype(np.float32) * bf, 0, 255).astype(np.uint8)

    return img


def generate(out_dir: str) -> None:
    out = Path(out_dir)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    ground_truth = []
    for sample in SYNTHETIC_SAMPLES:
        scene = _draw_synthetic_scene(sample)
        filename = f"{sample['id']}.jpg"
        path = str(img_dir / filename)
        cv2.imwrite(path, scene)

        ground_truth.append({
            "filename": filename,
            "violations": sample["violations"],
            "plate": sample["plate"],
            "severity": sample["severity"],
        })
        print(f"  Generated {filename}  violations={len(sample['violations'])}")

    gt_path = str(out / "ground_truth.json")
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"\nEval set written to: {out_dir}/")
    print(f"  {len(SYNTHETIC_SAMPLES)} synthetic images + ground_truth.json")
    print(
        "\nNOTE: These are OpenCV-drawn synthetic scenes — NOT real traffic images.\n"
        "      For real accuracy numbers supply your own photos and update ground_truth.json."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate synthetic eval set (no external data)")
    p.add_argument("--out-dir", default="eval_set", help="Output directory")
    args = p.parse_args()
    generate(args.out_dir)
