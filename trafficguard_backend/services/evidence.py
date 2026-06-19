"""
services/evidence.py

Generates:
  1. Annotated PNG  — watermark + per-violation text labels
     (bounding_hint is text, not pixel coords, so we render text overlays)
  2. court-ready PDF — case ID + QR code, timestamp, camera info, plate,
     violations, nearest police station, embedded annotated image
"""
from __future__ import annotations
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)

from config import EVIDENCE_DIR

log = logging.getLogger(__name__)

_SEV_COLORS = {"HIGH": (186, 26, 26), "MEDIUM": (230, 81, 0), "LOW": (161, 117, 0)}
_SEV_BG = {"HIGH": colors.HexColor("#ffdad6"), "MEDIUM": colors.HexColor("#ffe0b2"), "LOW": colors.HexColor("#fff9c4")}


# ── Annotated PNG ──────────────────────────────────────────────────────────

def create_annotated_image(
    image_bytes: bytes,
    case_id: str,
    violations: list[dict],
    plate: str | None,
    camera_id: str,
    timestamp: str,
) -> bytes:
    """
    Overlay violation labels, plate, camera info, and watermark on the image.
    Returns annotated JPEG bytes.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image for annotation")

    h, w = img.shape[:2]
    overlay = img.copy()

    # ── Dark semi-transparent header bar
    cv2.rectangle(overlay, (0, 0), (w, 52), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, f"TrafficGuard AI  |  {camera_id}  |  {timestamp}",
                (10, 18), font, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, f"Case: {case_id}", (10, 38),
                font, 0.45, (255, 213, 0), 1, cv2.LINE_AA)

    # ── Per-violation text labels
    y_offset = 80
    for v in violations:
        sev = v.get("severity", "MEDIUM")
        color_bgr = tuple(reversed(_SEV_COLORS.get(sev, (200, 200, 0))))
        label = f"[{sev}] {v['type'].replace('_',' ').upper()}  conf:{v['confidence']:.2f}"
        hint = v.get("bounding_hint", "")
        cv2.putText(img, label, (10, y_offset), font, 0.5, color_bgr, 1, cv2.LINE_AA)
        if hint:
            cv2.putText(img, f"  -> {hint}", (10, y_offset + 18),
                        font, 0.38, (200, 200, 200), 1, cv2.LINE_AA)
        y_offset += 40

    # ── Plate text in bottom-left
    if plate:
        cv2.rectangle(img, (0, h - 36), (w, h), (0, 0, 0), -1)
        cv2.putText(img, f"PLATE: {plate}", (10, h - 10),
                    font, 0.7, (255, 213, 0), 2, cv2.LINE_AA)

    # ── Watermark diagonal
    wm_overlay = img.copy()
    cv2.putText(wm_overlay, "BENGALURU TRAFFIC POLICE",
                (w // 6, h // 2), font, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.addWeighted(wm_overlay, 0.08, img, 0.92, 0, img)

    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()


# ── QR code ────────────────────────────────────────────────────────────────

def _make_qr_image(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Evidence PDF ────────────────────────────────────────────────────────────

def create_evidence_pdf(
    case_id: str,
    camera_id: str,
    camera_trust_score: float,
    timestamp: str,
    location_name: str | None,
    plate: str | None,
    plate_confidence: float | None,
    plate_valid: bool,
    severity: str,
    violations: list[dict],
    summary: str | None,
    station_name: str | None,
    station_distance_km: float | None,
    station_eta_minutes: float | None,
    annotated_image_bytes: bytes | None,
) -> bytes:
    """Generate a court-ready A4 PDF and return as bytes."""
    buf = io.BytesIO()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TGTitle", parent=styles["Heading1"],
        textColor=colors.HexColor("#0056c3"), fontSize=16, spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "TGHeading", parent=styles["Heading2"],
        textColor=colors.HexColor("#1b1c1c"), fontSize=12, spaceAfter=4,
    )
    body_style = styles["Normal"]
    body_style.fontSize = 10

    story = []

    # ── Title + QR side-by-side
    qr_buf = _make_qr_image(case_id)
    qr_img = RLImage(qr_buf, width=3 * cm, height=3 * cm)

    title_table = Table(
        [[Paragraph("TrafficGuard AI — Evidence Report", title_style), qr_img]],
        colWidths=[14 * cm, 3.5 * cm],
    )
    title_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(title_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Case metadata
    story.append(Paragraph("Case Details", heading_style))
    meta = [
        ["Case ID", case_id],
        ["Timestamp (UTC)", timestamp],
        ["Camera ID", camera_id],
        ["Camera Trust Score", f"{camera_trust_score:.2f}"],
        ["Location", location_name or "Unknown"],
        ["Severity", severity],
        ["Status", "Evidence Report"],
    ]
    meta_table = Table(meta, colWidths=[5 * cm, 12 * cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f3f2")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c2c6d6")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f6f3f2")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Plate
    story.append(Paragraph("License Plate", heading_style))
    plate_data = [
        ["Plate Number", plate or "Not detected"],
        ["Confidence", f"{plate_confidence:.2f}" if plate_confidence else "N/A"],
        ["Valid", "YES" if plate_valid else "NO"],
    ]
    plate_table = Table(plate_data, colWidths=[5 * cm, 12 * cm])
    plate_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f3f2")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c2c6d6")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(plate_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Violations
    story.append(Paragraph("Detected Violations", heading_style))
    viol_rows = [["#", "Type", "Severity", "Confidence", "Signal State", "Description"]]
    for i, v in enumerate(violations, 1):
        viol_rows.append([
            str(i),
            v["type"].replace("_", " ").title(),
            v["severity"],
            f"{v['confidence']:.2f}",
            v.get("signal_state") or "—",
            v.get("description", "")[:80],
        ])
    viol_table = Table(viol_rows, colWidths=[0.7 * cm, 4 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 6.2 * cm])
    viol_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0056c3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c2c6d6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f3f2")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(viol_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Summary
    if summary:
        story.append(Paragraph("AI Summary", heading_style))
        story.append(Paragraph(summary, body_style))
        story.append(Spacer(1, 0.4 * cm))

    # ── Nearest police station
    if station_name:
        story.append(Paragraph("Nearest Police Station", heading_style))
        station_data = [
            ["Station", station_name],
            ["Distance", f"{station_distance_km:.2f} km" if station_distance_km else "N/A"],
            ["ETA", f"{station_eta_minutes:.1f} min" if station_eta_minutes else "N/A"],
        ]
        st_table = Table(station_data, colWidths=[5 * cm, 12 * cm])
        st_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f3f2")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c2c6d6")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(st_table)
        story.append(Spacer(1, 0.4 * cm))

    # ── Annotated image
    if annotated_image_bytes:
        story.append(Paragraph("Annotated Evidence Frame", heading_style))
        img_buf = io.BytesIO(annotated_image_bytes)
        rl_img = RLImage(img_buf, width=17 * cm, height=10 * cm)
        story.append(rl_img)

    # ── Footer
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<font size='7' color='grey'>"
        "This document is generated by TrafficGuard AI and is intended for official use only. "
        "Bengaluru Traffic Police — Automated Enforcement Unit."
        "</font>",
        styles["Normal"],
    ))

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    doc.build(story)
    return buf.getvalue()


# ── Persist helpers ─────────────────────────────────────────────────────────

def save_evidence_files(
    case_id: str,
    annotated_bytes: bytes,
    pdf_bytes: bytes,
) -> tuple[str, str]:
    """
    Write annotated image + PDF to disk under evidence_output/{case_id}/.
    Returns (annotated_image_path, pdf_path).
    """
    out_dir = Path(EVIDENCE_DIR) / case_id
    out_dir.mkdir(parents=True, exist_ok=True)

    img_path = str(out_dir / "annotated.jpg")
    pdf_path = str(out_dir / "report.pdf")

    with open(img_path, "wb") as f:
        f.write(annotated_bytes)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    return img_path, pdf_path
