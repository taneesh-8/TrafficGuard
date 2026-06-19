"""
routes/analytics.py

GET /analytics/summary
GET /analytics/heatmap
GET /analytics/reoffenders
GET /analytics/trends
"""
from __future__ import annotations
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import APIRouter

from config import REOFFENDER_WINDOW_DAYS
from database import db_context
from models import AnalyticsSummary, HeatmapPoint, ReoffenderRecord, TrendPoint

log = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics")


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary():
    async with db_context() as db:
        async with db.execute("SELECT * FROM violations") as cur:
            rows = await cur.fetchall()

    by_type:   dict[str, int] = defaultdict(int)
    by_day:    dict[str, int] = defaultdict(int)
    by_hour:   dict[str, int] = defaultdict(int)
    by_camera: dict[str, int] = defaultdict(int)
    total_challans = 0

    for row in rows:
        row = dict(row)
        for v in json.loads(row.get("violations_json") or "[]"):
            by_type[v.get("type", "unknown")] += 1
        ts = row.get("first_seen", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                by_day[dt.strftime("%Y-%m-%d")] += 1
                by_hour[str(dt.hour)] += 1
            except Exception:
                pass
        by_camera[row.get("camera_id") or "unknown"] += 1
        if row.get("challan_issued"):
            total_challans += 1

    cutoff = (datetime.now(timezone.utc) - timedelta(days=REOFFENDER_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    async with db_context() as db:
        async with db.execute(
            "SELECT plate, COUNT(*) as cnt FROM violations "
            "WHERE plate IS NOT NULL AND first_seen >= ? GROUP BY plate HAVING cnt >= 3",
            (cutoff,),
        ) as cur:
            reoffender_rows = await cur.fetchall()

    return AnalyticsSummary(
        by_violation_type=dict(by_type),
        by_day=dict(by_day),
        by_hour=dict(by_hour),
        by_camera=dict(by_camera),
        total_cases=len(rows),
        total_challans=total_challans,
        total_reoffenders=len(reoffender_rows),
    )


@router.get("/heatmap", response_model=List[HeatmapPoint])
async def analytics_heatmap():
    async with db_context() as db:
        async with db.execute(
            "SELECT lat, lng, severity, COUNT(*) as cnt FROM violations "
            "WHERE lat IS NOT NULL AND lng IS NOT NULL GROUP BY lat, lng, severity"
        ) as cur:
            rows = await cur.fetchall()
    return [HeatmapPoint(lat=r["lat"], lng=r["lng"], count=r["cnt"], severity=r["severity"] or "LOW")
            for r in rows]


@router.get("/reoffenders", response_model=List[ReoffenderRecord])
async def analytics_reoffenders():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=REOFFENDER_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    async with db_context() as db:
        async with db.execute(
            """
            SELECT plate, COUNT(*) as offense_count,
                   MAX(last_seen) as last_seen,
                   GROUP_CONCAT(location_name, '||') as locations,
                   GROUP_CONCAT(case_id, '||') as case_ids
            FROM violations
            WHERE plate IS NOT NULL AND first_seen >= ?
            GROUP BY plate HAVING offense_count >= 3
            ORDER BY offense_count DESC
            """,
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

    results = []
    for r in rows:
        count = r["offense_count"]
        locs  = list({l for l in (r["locations"] or "").split("||") if l})
        ids   = list({i for i in (r["case_ids"]  or "").split("||") if i})
        risk  = "CRITICAL" if count >= 5 else "HIGH"
        results.append(ReoffenderRecord(
            plate=r["plate"], offense_count=count, last_seen=r["last_seen"],
            locations=locs, case_ids=ids, risk_level=risk,
        ))
    return results


@router.get("/trends", response_model=List[TrendPoint])
async def analytics_trends():
    today = datetime.now(timezone.utc)
    days  = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    async with db_context() as db:
        async with db.execute(
            "SELECT strftime('%Y-%m-%d', first_seen) as day, COUNT(*) as cnt "
            "FROM violations WHERE first_seen >= ? GROUP BY day",
            ((today - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),),
        ) as cur:
            rows = await cur.fetchall()
    count_map = {r["day"]: r["cnt"] for r in rows}
    return [TrendPoint(date=d, count=count_map.get(d, 0)) for d in days]
