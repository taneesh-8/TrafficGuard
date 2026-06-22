"""
services/deduplication.py

10-minute incident clustering: same plate + same camera within a rolling
DEDUP_WINDOW_MINUTES window → merge into the SAME case instead of creating
a new row (extend last_seen, increment frame_count, keep higher-confidence
reading per violation type).

No plate → always a new case.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta

import aiosqlite

from config import DEDUP_WINDOW_MINUTES

log = logging.getLogger(__name__)


async def find_existing_case(
    db: aiosqlite.Connection,
    plate: str | None,
    camera_id: str,
) -> dict | None:
    """
    Return the most-recent open case for this plate+camera within the
    dedup window, or None if no such case exists.
    """
    if not plate:
        return None   # no plate → always new case

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    async with db.execute(
        """
        SELECT * FROM violations
        WHERE plate = ? AND camera_id = ? AND last_seen >= ?
        ORDER BY last_seen DESC
        LIMIT 1
        """,
        (plate, camera_id, cutoff_str),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None
    return dict(row)


async def merge_into_existing(
    db: aiosqlite.Connection,
    existing: dict,
    new_violations: list[dict],
    new_scene: str | None,
    now_str: str,
    raw_image_path: str | None,
    enhanced_image_path: str | None,
) -> dict:
    """
    Merge new detection data into an existing case:
    - Increment frame_count
    - Update last_seen
    - Keep higher-confidence reading per violation type
    - Update scene_condition if provided
    """
    existing_violations: list[dict] = json.loads(existing.get("violations_json") or "[]")

    # Build a map of existing violations keyed by type
    viol_map: dict[str, dict] = {v["type"]: v for v in existing_violations}

    for new_v in new_violations:
        vtype = new_v["type"]
        if vtype not in viol_map or new_v["confidence"] > viol_map[vtype]["confidence"]:
            viol_map[vtype] = new_v

    merged_violations = list(viol_map.values())
    new_violations_json = json.dumps(merged_violations)
    new_frame_count = existing.get("frame_count", 1) + 1

    update_fields: dict[str, object] = {
        "violations_json": new_violations_json,
        "frame_count": new_frame_count,
        "last_seen": now_str,
        "updated_at": now_str,
    }
    if new_scene:
        update_fields["scene_condition"] = new_scene
    if raw_image_path:
        update_fields["raw_image_path"] = raw_image_path
    if enhanced_image_path:
        update_fields["enhanced_image_path"] = enhanced_image_path

    set_clause = ", ".join(f"{k} = ?" for k in update_fields)
    values = list(update_fields.values()) + [existing["case_id"]]
    await db.execute(
        f"UPDATE violations SET {set_clause} WHERE case_id = ?",
        values,
    )
    await db.commit()

    log.info(
        "Merged frame into existing case %s (frame_count=%d)",
        existing["case_id"],
        new_frame_count,
    )

    # Return the updated row
    async with db.execute(
        "SELECT * FROM violations WHERE case_id = ?", (existing["case_id"],)
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row)
