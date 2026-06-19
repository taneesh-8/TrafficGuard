"""Central configuration — reads from .env / environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str          = os.getenv("GEMINI_API_KEY", "")
GEMINI_VISION_MODEL: str     = os.getenv("GEMINI_VISION_MODEL", "gemini-1.5-flash")

# ── MapMyIndia ────────────────────────────────────────────────────────────────
# Static REST key (preferred — skips OAuth2)
MAPMYINDIA_REST_KEY: str     = os.getenv("MAPMYINDIA_REST_KEY", "")
# OAuth2 credentials (used only when REST key is absent)
MAPMYINDIA_CLIENT_ID: str    = os.getenv("MAPMYINDIA_CLIENT_ID", "")
MAPMYINDIA_CLIENT_SECRET: str = os.getenv("MAPMYINDIA_CLIENT_SECRET", "")

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "trafficguard.db")

# ── Business-logic knobs ──────────────────────────────────────────────────────
AUTO_CHALLAN_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("AUTO_CHALLAN_CONFIDENCE_THRESHOLD", "0.92")
)
DEDUP_WINDOW_MINUTES: int  = int(os.getenv("DEDUP_WINDOW_MINUTES", "10"))
REOFFENDER_WINDOW_DAYS: int = int(os.getenv("REOFFENDER_WINDOW_DAYS", "7"))
LOW_LIGHT_THRESHOLD: int   = int(os.getenv("LOW_LIGHT_THRESHOLD", "60"))

UPLOADS_DIR: str  = os.getenv("UPLOADS_DIR", "uploads")
EVIDENCE_DIR: str = os.getenv("EVIDENCE_DIR", "evidence_output")
