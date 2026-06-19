"""
evaluate.py

Runs the TrafficGuard AI analysis pipeline against a labeled eval set and
computes per-violation-type and overall Accuracy, Precision, Recall, F1.
Also measures throughput (images/sec, p50/p95 latency).

NOTE: bounding_hint is text-based, NOT pixel coordinates, so true IoU-based
      mAP cannot be computed. A confidence-bucketed precision/recall curve
      is provided as a proxy.

Usage:
    python evaluate.py --dataset eval_set/   [--output metrics.json]

The eval set must contain:
    images/          ← JPEG/PNG files
    ground_truth.json ← [{filename, violations:[{type,...}], plate, severity}]

This script calls service functions directly (no HTTP), so the backend
server does NOT need to be running.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# ── Make project root importable ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from services.claude_vision import analyze_image
from utils.severity import case_severity

VIOLATION_TYPES = [
    "helmet_non_compliance", "seatbelt", "triple_riding",
    "wrong_side", "stop_line", "red_light", "illegal_parking",
]


async def _run_sample(image_bytes: bytes) -> dict[str, Any]:
    result, _, _ = await analyze_image(image_bytes)
    return result


def _predicted_types(result: dict) -> set[str]:
    return {v["type"] for v in result.get("violations", [])}


def _confidence_buckets(
    predicted_violations: list[dict],
    gt_types: set[str],
    buckets: list[float],
) -> list[dict]:
    """
    For each confidence threshold bucket, compute precision/recall across
    all violation predictions.
    NOTE: This is an approximation — true mAP requires IoU.
    """
    records = []
    for thresh in buckets:
        tp = fp = fn = 0
        for v in predicted_violations:
            if v["confidence"] >= thresh:
                if v["type"] in gt_types:
                    tp += 1
                else:
                    fp += 1
        for gt in gt_types:
            found = any(
                v["type"] == gt and v["confidence"] >= thresh
                for v in predicted_violations
            )
            if not found:
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        records.append({"threshold": thresh, "precision": prec, "recall": rec, "tp": tp, "fp": fp, "fn": fn})
    return records


def evaluate(dataset_dir: str, output_path: str) -> None:
    dataset = Path(dataset_dir)
    gt_path = dataset / "ground_truth.json"
    if not gt_path.exists():
        print(f"ERROR: ground_truth.json not found in {dataset_dir}")
        sys.exit(1)

    with open(gt_path) as f:
        ground_truth: list[dict] = json.load(f)

    print(f"Evaluating {len(ground_truth)} samples from {dataset_dir}/images/...")
    print("(Calls Claude Vision API — ANTHROPIC_API_KEY must be set)\n")

    latencies: list[float] = []
    per_type_tp: dict[str, int] = defaultdict(int)
    per_type_fp: dict[str, int] = defaultdict(int)
    per_type_fn: dict[str, int] = defaultdict(int)
    all_predictions: list[dict] = []
    all_gt_types:    list[set]  = []
    severity_correct = 0

    for sample in ground_truth:
        img_path = dataset / "images" / sample["filename"]
        if not img_path.exists():
            print(f"  SKIP {sample['filename']} — file not found")
            continue

        with open(img_path, "rb") as f:
            img_bytes = f.read()

        t0 = time.perf_counter()
        try:
            result = asyncio.run(_run_sample(img_bytes))
        except Exception as exc:
            print(f"  ERROR {sample['filename']}: {exc}")
            continue
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)

        gt_types     = {v["type"] for v in sample.get("violations", [])}
        pred_types   = _predicted_types(result)
        pred_viols   = result.get("violations", [])

        all_predictions.append({"violations": pred_viols, "severity": result.get("violations", [])})
        all_gt_types.append(gt_types)

        # Per-type TP/FP/FN
        for vtype in VIOLATION_TYPES:
            gt_has  = vtype in gt_types
            pred_has = vtype in pred_types
            if gt_has and pred_has:
                per_type_tp[vtype] += 1
            elif (not gt_has) and pred_has:
                per_type_fp[vtype] += 1
            elif gt_has and (not pred_has):
                per_type_fn[vtype] += 1

        # Severity
        pred_sev = case_severity([v["severity"] for v in pred_viols])
        if pred_sev == sample.get("severity", "LOW"):
            severity_correct += 1

        print(
            f"  {sample['filename']:20s}  gt={sorted(gt_types)!s:50s}  "
            f"pred={sorted(pred_types)!s:50s}  {elapsed:.2f}s"
        )

    if not latencies:
        print("\nNo samples were evaluated.")
        return

    # ── Per-type metrics ──────────────────────────────────────────────────────
    per_type_metrics: dict[str, dict] = {}
    for vtype in VIOLATION_TYPES:
        tp = per_type_tp[vtype]
        fp = per_type_fp[vtype]
        fn = per_type_fn[vtype]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_type_metrics[vtype] = {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}

    # ── Overall metrics ───────────────────────────────────────────────────────
    total_tp = sum(per_type_tp.values())
    total_fp = sum(per_type_fp.values())
    total_fn = sum(per_type_fn.values())
    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_rec  = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1   = 2 * overall_prec * overall_rec / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0
    accuracy     = total_tp / (total_tp + total_fp + total_fn) if (total_tp + total_fp + total_fn) > 0 else 0.0

    # ── Confidence-bucketed curve (proxy for mAP) ─────────────────────────────
    buckets = [round(0.5 + i * 0.05, 2) for i in range(11)]   # 0.50 … 1.00
    all_pred_viols_flat = [v for s in all_predictions for v in s["violations"]]
    all_gt_flat = set()
    for gt_set in all_gt_types:
        all_gt_flat.update(gt_set)
    bucket_curve = _confidence_buckets(all_pred_viols_flat, all_gt_flat, buckets)

    # ── Throughput ────────────────────────────────────────────────────────────
    sorted_lat = sorted(latencies)
    n = len(sorted_lat)
    p50 = sorted_lat[n // 2]
    p95 = sorted_lat[min(int(n * 0.95), n - 1)]
    throughput = n / sum(latencies)

    # ── Severity accuracy ─────────────────────────────────────────────────────
    sev_acc = severity_correct / len(ground_truth) if ground_truth else 0.0

    # ── Assemble metrics ──────────────────────────────────────────────────────
    metrics = {
        "overall": {
            "accuracy":  round(accuracy, 4),
            "precision": round(overall_prec, 4),
            "recall":    round(overall_rec, 4),
            "f1":        round(overall_f1, 4),
            "severity_accuracy": round(sev_acc, 4),
        },
        "per_violation_type": {
            k: {mk: round(mv, 4) for mk, mv in v.items()}
            for k, v in per_type_metrics.items()
        },
        "throughput": {
            "images_per_second": round(throughput, 3),
            "p50_latency_s": round(p50, 3),
            "p95_latency_s": round(p95, 3),
            "total_samples": n,
            "note": (
                "Latency dominated by Claude API round-trip. "
                "bounding_hint is text, not pixel coords — true IoU-based mAP not possible."
            ),
        },
        "confidence_curve": bucket_curve,
    }

    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"  Overall   Accuracy={accuracy:.3f}  Precision={overall_prec:.3f}  "
          f"Recall={overall_rec:.3f}  F1={overall_f1:.3f}")
    print(f"  Severity  Accuracy={sev_acc:.3f}")
    print(f"  Throughput {throughput:.2f} img/s  |  p50={p50:.2f}s  p95={p95:.2f}s")
    print()
    print(f"  {'Violation Type':30s}  {'Prec':6s}  {'Rec':6s}  {'F1':6s}")
    print("  " + "-" * 55)
    for vtype, m in per_type_metrics.items():
        print(f"  {vtype:30s}  {m['precision']:.3f}   {m['recall']:.3f}   {m['f1']:.3f}")
    print()
    print(f"  Full metrics saved to: {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Evaluate TrafficGuard AI pipeline")
    p.add_argument("--dataset", required=True, help="Path to eval set directory")
    p.add_argument("--output",  default="metrics.json", help="Output metrics JSON path")
    args = p.parse_args()
    evaluate(args.dataset, args.output)
