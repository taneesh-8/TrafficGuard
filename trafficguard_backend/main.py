"""
main.py — TrafficGuard AI FastAPI application

Run with:
    uvicorn main:app --reload
"""
from __future__ import annotations
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS, UPLOADS_DIR, EVIDENCE_DIR
from database import init_db
from routes.violations import router as violations_router
from routes.analytics  import router as analytics_router
from routes.dispatch   import router as dispatch_router
from ws_manager import manager

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TrafficGuard AI",
    description="AI-powered traffic violation detection for Bengaluru Traffic Police",
    version="2.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In development we allow all origins so IPv4/IPv6 localhost variants all work.
# In production, set CORS_ORIGINS in .env to restrict this.
_cors_origins = CORS_ORIGINS if CORS_ORIGINS else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file mounts ────────────────────────────────────────────────────────
os.makedirs(UPLOADS_DIR,  exist_ok=True)
os.makedirs(EVIDENCE_DIR, exist_ok=True)
app.mount("/uploads",         StaticFiles(directory=UPLOADS_DIR),  name="uploads")
app.mount("/evidence_output", StaticFiles(directory=EVIDENCE_DIR), name="evidence_output")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(violations_router)
app.include_router(analytics_router)
app.include_router(dispatch_router)


# ── DB init ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()
    log.info("TrafficGuard AI started — DB initialised, seed cameras loaded.")


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/violations")
async def ws_violations(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; clients can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "TrafficGuard AI"}
