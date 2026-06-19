"""
routes/violations.py

POST /analyze
GET  /violations
GET  /violations/{case_id}
GET  /evidence/{case_id}/pdf
GET  /evidence/{case_id}/image
"""
from __future__ import annotations
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from config import UPLOADS_DIR, EVIDENCE_DIR, REOFFENDER_WINDOW_DAYS
from database import db_context
from models import (
    AnalyzeResponse, MapPin, ReoffenderInfo,
    PaginatedViolations, ViolationCase, ViolationItem, VehicleItem,
)
from services import gemini_vision, deduplication, evidence, mapmyindia
from utils.challan import evaluate_challan
from utils.severity import case_severity
from ws_manager import manager

log = logging.getLogger(__name__)
router = APIRouter()

PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_case_id() -> str:
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:6].upper()
    return f"TG-{now.strftime('%Y%m%d')}-{suffix}"


def _validate_plate(plate: str | None) -> bool:
    if not plate:
        return False
    clean = plate.replace(" ", "").upper()
    return bool(PLATE_REGEX.match(clean))


def _row_to_violation_case(row: dict) -> ViolationCase:
    violations = [ViolationItem(**v) for v in json.loads(row.get("violations_json") or "[]")]
    vehicles   = [VehicleItem(**v)   for v in json.loads(row.get("vehicles_json")   or "[]")]
    return ViolationCase(
        case_id=row["case_id"],
        camera_id=row.get("camera_id"),
        lat=row.get("lat"),
        lng=row.get("lng"),
        location_name=row.get("location_name"),
        plate=row.get("plate"),
        plate_confidence=row.get("plate_confidence"),
        plate_valid=bool(row.get("plate_valid")),
        scene_condition=row.get("scene_condition"),
        vehicles=vehicles,
        violations=violations,
        severity=row.get("severity"),
        summary=row.get("summary"),
        status=row.get("status", "pending_review"),
        challan_issued=bool(row.get("challan_issued")),
        review_reason=row.get("review_reason"),
        first_seen=row.get("first_seen"),
        last_seen=row.get("last_seen"),
        frame_count=row.get("frame_count", 1),
        image_url=f"/evidence/{row['case_id']}/image" if row.get("annotated_image_path") else None,
        annotated_image_url=f"/evidence/{row['case_id']}/image" if row.get("annotated_image_path") else None,
        pdf_url=f"/evidence/{row['case_id']}/pdf" if row.get("pdf_path") else None,
    )


async def _get_reoffender_info(plate: str) -> ReoffenderInfo | None:
    if not plate:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=REOFFENDER_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    async with db_context() as db:
        async with db.execute(
            "SELECT case_id, location_name FROM violations WHERE plate = ? AND first_seen >= ?",
            (plate, cutoff),
        ) as cur:
            rows = await cur.fetchall()
    if len(rows) < 3:
        return None
    case_ids  = [r["case_id"] for r in rows]
    locations = list({r["location_name"] for r in rows if r.get("location_name")})
    return ReoffenderInfo(plate=plate, offense_count=len(rows), locations=locations, case_ids=case_ids)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    file:      UploadFile       = File(...),
    camera_id: str              = Form("CAM_UNKNOWN"),
    lat:       Optional[float]  = Form(None),
    lng:       Optional[float]  = Form(None),
):
    now = _now_utc()
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file")

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    raw_filename = f"{uuid.uuid4().hex}_{file.filename or 'frame.jpg'}"
    raw_path = os.path.join(UPLOADS_DIR, raw_filename)
    with open(raw_path, "wb") as f:
        f.write(image_bytes)

    # ── Gemini vision (two-pass) ────────────────────────────────────────────
    try:
        result, raw_bytes, enhanced_bytes = await gemini_vision.analyze_image(image_bytes)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.error("Gemini vision failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Vision analysis failed: {exc}")

    enhanced_path: str | None = None
    if enhanced_bytes:
        enh_filename = f"enh_{raw_filename}"
        enhanced_path = os.path.join(UPLOADS_DIR, enh_filename)
        with open(enhanced_path, "wb") as f:
            f.write(enhanced_bytes)

    violations_raw: list[dict] = result.get("violations", [])
    vehicles_raw:   list[dict] = result.get("vehicles", [])
    scene_cond:     str | None = result.get("scene_condition")
    plate_raw:      str | None = result.get("license_plate")
    plate_conf:     float      = float(result.get("plate_confidence") or 0.0)
    summary:        str | None = result.get("summary")

    plate_clean = plate_raw.replace(" ", "").upper() if plate_raw else None
    plate_valid = _validate_plate(plate_clean)

    # ── No violations ────────────────────────────────────────────────────────
    if not violations_raw:
        return AnalyzeResponse(
            case_id="", is_new_case=False, camera_id=camera_id,
            location_name=None, plate=plate_clean, plate_valid=plate_valid,
            scene_condition=scene_cond, violations=[], severity="LOW",
            summary=summary, status="no_violation", challan_issued=False,
            review_reason=None, pdf_url=None, image_url=None, map_pin=None, reoffender=None,
        )

    # ── Resolve location ────────────────────────────────────────────────────
    loc_lat, loc_lng = lat, lng
    if loc_lat is None or loc_lng is None:
        async with db_context() as db:
            async with db.execute(
                "SELECT lat, lng FROM cameras WHERE camera_id = ?", (camera_id,)
            ) as cur:
                cam_row = await cur.fetchone()
        if cam_row:
            loc_lat, loc_lng = cam_row["lat"], cam_row["lng"]

    location_name: str | None = None
    if loc_lat is not None and loc_lng is not None:
        location_name = await mapmyindia.reverse_geocode(loc_lat, loc_lng)

    # ── Camera info ──────────────────────────────────────────────────────────
    async with db_context() as db:
        async with db.execute(
            "SELECT trust_score, status FROM cameras WHERE camera_id = ?", (camera_id,)
        ) as cur:
            cam_info = await cur.fetchone()

    trust_score = float(cam_info["trust_score"]) if cam_info else 0.0
    cam_status  = cam_info["status"] if cam_info else "unknown"
    if cam_status == "maintenance":
        trust_score = 0.0

    sev_list    = [v["severity"] for v in violations_raw]
    overall_sev = case_severity(sev_list)
    max_conf    = max((v["confidence"] for v in violations_raw), default=0.0)

    challan_issued, status, review_reason = evaluate_challan(
        max_confidence=max_conf,
        plate_valid=plate_valid,
        case_severity=overall_sev,
        camera_trust_score=trust_score,
    )

    # ── Deduplication ────────────────────────────────────────────────────────
    async with db_context() as db:
        existing = await deduplication.find_existing_case(db, plate_clean, camera_id)

        if existing:
            updated  = await deduplication.merge_into_existing(
                db, existing, violations_raw, scene_cond, now, raw_path, enhanced_path
            )
            case_id  = updated["case_id"]
            is_new   = False
            final_row = updated
        else:
            case_id = _make_case_id()
            is_new  = True
            await db.execute(
                """
                INSERT INTO violations
                    (case_id, camera_id, lat, lng, location_name, plate, plate_confidence,
                     plate_valid, scene_condition, vehicles_json, violations_json, severity,
                     summary, raw_image_path, enhanced_image_path, status, challan_issued,
                     review_reason, first_seen, last_seen, frame_count, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
                """,
                (
                    case_id, camera_id, loc_lat, loc_lng, location_name,
                    plate_clean, plate_conf, int(plate_valid), scene_cond,
                    json.dumps(vehicles_raw), json.dumps(violations_raw),
                    overall_sev, summary, raw_path, enhanced_path,
                    status, int(challan_issued), review_reason,
                    now, now, now, now,
                ),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM violations WHERE case_id = ?", (case_id,)
            ) as cur:
                final_row = dict(await cur.fetchone())

        await db.execute(
            "UPDATE cameras SET detections_count = detections_count + 1 WHERE camera_id = ?",
            (camera_id,),
        )
        await db.commit()

    # ── Evidence generation ──────────────────────────────────────────────────
    annotated_path: str | None = None
    pdf_path:       str | None = None
    annotated_bytes = None

    try:
        annotated_bytes = evidence.create_annotated_image(
            image_bytes=enhanced_bytes or image_bytes,
            case_id=case_id,
            violations=violations_raw,
            plate=plate_clean,
            camera_id=camera_id,
            timestamp=now,
        )
        station_info: dict = {}
        if loc_lat is not None and loc_lng is not None:
            station_info = await mapmyindia.nearest_police_station(loc_lat, loc_lng)

        pdf_bytes = evidence.create_evidence_pdf(
            case_id=case_id, camera_id=camera_id, camera_trust_score=trust_score,
            timestamp=now, location_name=location_name,
            plate=plate_clean, plate_confidence=plate_conf, plate_valid=plate_valid,
            severity=overall_sev, violations=violations_raw, summary=summary,
            station_name=station_info.get("station_name"),
            station_distance_km=station_info.get("distance_km"),
            station_eta_minutes=station_info.get("eta_minutes"),
            annotated_image_bytes=annotated_bytes,
        )
        annotated_path, pdf_path = evidence.save_evidence_files(case_id, annotated_bytes, pdf_bytes)

        async with db_context() as db:
            await db.execute(
                "UPDATE violations SET annotated_image_path=?, pdf_path=?, updated_at=? WHERE case_id=?",
                (annotated_path, pdf_path, now, case_id),
            )
            await db.commit()
    except Exception as exc:
        log.error("Evidence generation failed for %s: %s", case_id, exc)

    reoffender = await _get_reoffender_info(plate_clean) if plate_clean else None

    violation_items = [ViolationItem(**v) for v in violations_raw]
    map_pin = (
        MapPin(lat=loc_lat, lng=loc_lng, severity=overall_sev, case_id=case_id)
        if loc_lat is not None and loc_lng is not None else None
    )

    response = AnalyzeResponse(
        case_id=case_id, is_new_case=is_new, camera_id=camera_id,
        location_name=location_name, plate=plate_clean, plate_valid=plate_valid,
        scene_condition=scene_cond, violations=violation_items,
        severity=overall_sev, summary=summary, status=status,
        challan_issued=challan_issued, review_reason=review_reason,
        pdf_url=f"/evidence/{case_id}/pdf"   if pdf_path      else None,
        image_url=f"/evidence/{case_id}/image" if annotated_path else None,
        map_pin=map_pin, reoffender=reoffender,
    )

    await manager.broadcast(response.model_dump())
    return response


@router.get("/violations", response_model=PaginatedViolations)
async def list_violations(
    date_from:      Optional[str]  = Query(None),
    date_to:        Optional[str]  = Query(None),
    violation_type: Optional[str]  = Query(None),
    plate:          Optional[str]  = Query(None),
    severity:       Optional[str]  = Query(None),
    status:         Optional[str]  = Query(None),
    page:           int            = Query(1, ge=1),
    page_size:      int            = Query(20, ge=1, le=100),
):
    conditions, params = [], []
    if date_from:  conditions.append("first_seen >= ?"); params.append(date_from)
    if date_to:    conditions.append("first_seen <= ?"); params.append(date_to)
    if plate:      conditions.append("plate LIKE ?");    params.append(f"%{plate.upper()}%")
    if severity:   conditions.append("severity = ?");    params.append(severity.upper())
    if status:     conditions.append("status = ?");      params.append(status)

    where  = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size

    async with db_context() as db:
        async with db.execute(f"SELECT COUNT(*) as cnt FROM violations {where}", params) as cur:
            total = (await cur.fetchone())["cnt"]

        if violation_type:
            extra = f"{where} {'AND' if where else 'WHERE'} violations_json LIKE ?"
            async with db.execute(
                f"SELECT * FROM violations {extra} ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                params + [f'%"type": "{violation_type}"%', page_size, offset],
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                f"SELECT * FROM violations {where} ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                params + [page_size, offset],
            ) as cur:
                rows = await cur.fetchall()

    return PaginatedViolations(
        total=total, page=page, page_size=page_size,
        results=[_row_to_violation_case(dict(r)) for r in rows],
    )


@router.get("/violations/{case_id}", response_model=ViolationCase)
async def get_violation(case_id: str):
    async with db_context() as db:
        async with db.execute("SELECT * FROM violations WHERE case_id = ?", (case_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return _row_to_violation_case(dict(row))


@router.get("/evidence/{case_id}/pdf")
async def get_evidence_pdf(case_id: str):
    async with db_context() as db:
        async with db.execute("SELECT pdf_path FROM violations WHERE case_id = ?", (case_id,)) as cur:
            row = await cur.fetchone()
    if not row or not row["pdf_path"]:
        raise HTTPException(status_code=404, detail="PDF not found")
    if not os.path.exists(row["pdf_path"]):
        raise HTTPException(status_code=404, detail="PDF file missing from disk")
    return FileResponse(row["pdf_path"], media_type="application/pdf", filename=f"{case_id}.pdf")


@router.get("/evidence/{case_id}/image")
async def get_evidence_image(case_id: str):
    async with db_context() as db:
        async with db.execute(
            "SELECT annotated_image_path FROM violations WHERE case_id = ?", (case_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row or not row["annotated_image_path"]:
        raise HTTPException(status_code=404, detail="Image not found")
    if not os.path.exists(row["annotated_image_path"]):
        raise HTTPException(status_code=404, detail="Image file missing from disk")
    return FileResponse(row["annotated_image_path"], media_type="image/jpeg",
                        filename=f"{case_id}_annotated.jpg")
