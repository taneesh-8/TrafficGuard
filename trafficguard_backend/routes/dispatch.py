"""
routes/dispatch.py

POST /dispatch/suggest
GET  /cameras
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter

from database import db_context, row_dict
from models import CameraRecord, DispatchRequest, DispatchResponse
from services import mapmyindia

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/dispatch/suggest", response_model=DispatchResponse)
async def dispatch_suggest(body: DispatchRequest):
    station_info = await mapmyindia.nearest_police_station(body.lat, body.lng)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with db_context() as db:
        await db.execute(
            """
            INSERT INTO dispatch_log
                (hotspot_lat, hotspot_lng, station_name, distance_km, eta_minutes,
                 route_polyline, case_ids_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'suggested', ?)
            """,
            (
                body.lat, body.lng,
                station_info["station_name"],
                station_info["distance_km"],
                station_info["eta_minutes"],
                station_info.get("route_polyline"),
                json.dumps(body.case_ids or []),
                now,
            ),
        )
        await db.commit()

    return DispatchResponse(
        station_name=station_info["station_name"],
        distance_km=station_info["distance_km"],
        eta_minutes=station_info["eta_minutes"],
        route_polyline=station_info.get("route_polyline"),
        hotspot_lat=body.lat,
        hotspot_lng=body.lng,
    )


@router.get("/cameras", response_model=List[CameraRecord])
async def list_cameras():
    async with db_context() as db:
        async with db.execute("SELECT * FROM cameras ORDER BY camera_id") as cur:
            rows = await cur.fetchall()
    return [
        CameraRecord(**{k: row_dict(r)[k] for k in ["camera_id","location_name","lat","lng","trust_score","status","detections_count","false_positive_count"]})
        for r in rows
    ]
