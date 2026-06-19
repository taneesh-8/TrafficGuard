# TrafficGuard AI 2.0

AI-powered traffic violation detection system for Bengaluru Traffic Police.

## Architecture

```
Traffic Guard 2.0/
├── stitch_trafficguard_ai_dashboard/   # Frontend (static HTML + Tailwind)
│   └── stitch_trafficguard_ai_dashboard/
│       ├── live_feed_light_mode/       # Live camera feed with real video
│       ├── map_view_light_mode/        # Leaflet.js interactive map
│       ├── analytics_light_mode/       # Analytics dashboard
│       ├── dispatch_dark_mode/         # Dispatch recommendations
│       ├── upload_analyze/             # Upload & AI-analyze images
│       ├── evidence_modal_light_mode/  # Evidence viewer modal
│       ├── trafficguard_ai_global_theme_system/
│       └── assets/                     # Video feed assets
│
└── trafficguard_backend/               # FastAPI + SQLite backend
    ├── main.py
    ├── config.py
    ├── database.py
    ├── models.py
    ├── routes/
    │   ├── violations.py   # POST /analyze, GET /violations, evidence endpoints
    │   ├── analytics.py    # GET /analytics/*
    │   └── dispatch.py     # POST /dispatch/suggest, GET /cameras
    ├── services/
    │   ├── gemini_vision.py    # Google Gemini vision API (two-pass)
    │   ├── mapmyindia.py       # Mappls geocoding + routing
    │   ├── deduplication.py    # 10-min incident clustering
    │   └── evidence.py         # PDF + annotated image generation
    ├── utils/
    │   ├── preprocessing.py    # CLAHE + denoising
    │   ├── severity.py
    │   └── challan.py          # Auto-challan gate
    ├── tests/
    ├── camera_feed_simulator.py
    ├── generate_eval_set.py
    ├── evaluate.py
    ├── requirements.txt
    └── .env.example
```

## Quick Start

### Backend
```bash
cd trafficguard_backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add GEMINI_API_KEY from https://aistudio.google.com/app/apikey
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd stitch_trafficguard_ai_dashboard/stitch_trafficguard_ai_dashboard
npx serve . -l 3000
```

Then open `http://localhost:3000/live_feed_light_mode/code.html`

## Environment Variables

Copy `trafficguard_backend/.env.example` to `trafficguard_backend/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google Gemini API key (aistudio.google.com) |
| `GEMINI_VISION_MODEL` | Optional | Default: `gemini-2.0-flash` |
| `MAPMYINDIA_REST_KEY` | Optional | Mappls static REST key for real geocoding |
| `MAPMYINDIA_CLIENT_ID` | Optional | Mappls OAuth2 client ID |
| `MAPMYINDIA_CLIENT_SECRET` | Optional | Mappls OAuth2 client secret |
| `CORS_ORIGINS` | Optional | Comma-separated allowed origins |
| `DATABASE_PATH` | Optional | SQLite DB path (default: `trafficguard.db`) |

## Features

- **Live Feed** — Real looping traffic video with AI bounding boxes over detected violations via WebSocket
- **Interactive Map** — Leaflet.js + OpenStreetMap with live hotspot heatmap, camera markers, reoffender zones, signal status
- **Upload & Analyze** — Drag-and-drop image upload → Gemini Vision analysis → violation detection → evidence PDF
- **Analytics** — KPI dashboard with Export PDF (print) and Export CSV (from backend API)
- **Dispatch** — AI-recommended officer deployment with nearest police station routing
- **i18n** — English / ಕನ್ನಡ / हिंदी language switcher on all screens
- **Dark/Light mode** — Persisted via localStorage, toggle on every screen

## API

| Endpoint | Description |
|---|---|
| `POST /analyze` | Analyze a traffic image |
| `GET /violations` | List all cases with filters |
| `GET /evidence/{id}/pdf` | Download evidence PDF |
| `GET /analytics/summary` | Violation stats |
| `GET /analytics/heatmap` | GeoJSON heatmap data |
| `GET /cameras` | Camera status list |
| `POST /dispatch/suggest` | Nearest police station routing |
| `WS /ws/violations` | Real-time violation push |

## Tech Stack

**Frontend:** HTML5 · Tailwind CSS · Leaflet.js · Material Symbols · Vanilla JS  
**Backend:** FastAPI · SQLite (aiosqlite) · Google Gemini Vision · Mappls API · OpenCV · ReportLab · QRCode
