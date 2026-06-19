"""SQLite database initialization, schema, and async connection helper."""
import aiosqlite
from config import DATABASE_PATH
from contextlib import asynccontextmanager

# ── Schema ─────────────────────────────────────────────────────────────────

CREATE_CAMERAS = """
CREATE TABLE IF NOT EXISTS cameras (
    camera_id            TEXT PRIMARY KEY,
    location_name        TEXT,
    lat                  REAL,
    lng                  REAL,
    trust_score          REAL NOT NULL DEFAULT 0.9,
    status               TEXT NOT NULL DEFAULT 'active',
    detections_count     INTEGER NOT NULL DEFAULT 0,
    false_positive_count INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_VIOLATIONS = """
CREATE TABLE IF NOT EXISTS violations (
    case_id              TEXT PRIMARY KEY,
    camera_id            TEXT REFERENCES cameras(camera_id),
    lat                  REAL,
    lng                  REAL,
    location_name        TEXT,
    plate                TEXT,
    plate_confidence     REAL,
    plate_valid          INTEGER NOT NULL DEFAULT 0,
    scene_condition      TEXT,
    vehicles_json        TEXT,
    violations_json      TEXT,
    severity             TEXT,
    summary              TEXT,
    raw_image_path       TEXT,
    enhanced_image_path  TEXT,
    annotated_image_path TEXT,
    pdf_path             TEXT,
    status               TEXT NOT NULL DEFAULT 'pending_review',
    challan_issued       INTEGER NOT NULL DEFAULT 0,
    review_reason        TEXT,
    first_seen           TEXT,
    last_seen            TEXT,
    frame_count          INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT,
    updated_at           TEXT
);
"""

CREATE_DISPATCH_LOG = """
CREATE TABLE IF NOT EXISTS dispatch_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_lat     REAL,
    hotspot_lng     REAL,
    station_name    TEXT,
    distance_km     REAL,
    eta_minutes     REAL,
    route_polyline  TEXT,
    case_ids_json   TEXT,
    status          TEXT NOT NULL DEFAULT 'suggested',
    created_at      TEXT
);
"""

# ── Seed cameras ─────────────────────────────────────────────────────────────
# Six project-defined demo cameras around Bengaluru (not an external dataset)
SEED_CAMERAS = [
    ("CAM_047", "Silk Board Junction, Hosur Road",   12.9172, 77.6228, 0.94, "active"),
    ("CAM_012", "Marathahalli Bridge, Outer Ring Rd", 12.9591, 77.7001, 0.88, "active"),
    ("CAM_031", "Koramangala 80 Ft Road",             12.9352, 77.6245, 0.91, "active"),
    ("CAM_008", "Hebbal Flyover, Bellary Road",       13.0358, 77.5970, 0.76, "active"),
    ("CAM_055", "MG Road Metro Station",              12.9757, 77.6073, 0.62, "active"),
    ("CAM_099", "Indiranagar 12th Main",              12.9784, 77.6408, 0.50, "maintenance"),
]

async def get_db() -> aiosqlite.Connection:
    """
    Return an already-opened aiosqlite connection.
    Use as: async with await get_db() as db: ...
    Or open inline with: async with aiosqlite.connect(DATABASE_PATH) as db:
    """
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    return db


@asynccontextmanager
async def db_context():
    """Preferred: async context manager that always closes the connection."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        yield db


def row_dict(row) -> dict:
    """Convert an aiosqlite/sqlite3.Row to a plain dict safely."""
    if row is None:
        return {}
    return dict(row)

async def init_db() -> None:
    """Create tables and seed demo cameras on first run."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(CREATE_CAMERAS)
        await db.execute(CREATE_VIOLATIONS)
        await db.execute(CREATE_DISPATCH_LOG)
        await db.commit()

        for cam in SEED_CAMERAS:
            await db.execute(
                """
                INSERT OR IGNORE INTO cameras
                    (camera_id, location_name, lat, lng, trust_score, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                cam,
            )
        await db.commit()
