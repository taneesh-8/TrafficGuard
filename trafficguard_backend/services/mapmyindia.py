"""
services/mapmyindia.py

Primary path  : Mappls REST API
  - If MAPMYINDIA_REST_KEY is set → use as a static Bearer / REST key
    directly in every request header (no OAuth2 needed).
  - If only MAPMYINDIA_CLIENT_ID + SECRET are set → OAuth2 token flow.
Fallback path : hardcoded Bengaluru lookup table — fires ONLY when no
               Mappls credentials are present at all. A WARNING is logged
               every time the fallback fires.
"""
from __future__ import annotations
import logging
import time
import httpx
from config import MAPMYINDIA_REST_KEY, MAPMYINDIA_CLIENT_ID, MAPMYINDIA_CLIENT_SECRET

log = logging.getLogger(__name__)

# ── Token cache ───────────────────────────────────────────────────────────
_token: str | None = None
_token_expiry: float = 0.0

MAPPLS_TOKEN_URL = "https://outpost.mapmyindia.com/api/security/oauth/token"
MAPPLS_REVGEO_URL = "https://apis.mapmyindia.com/advancedmaps/v1/{key}/rev_geocode"
MAPPLS_NEARBY_URL = "https://atlas.mapmyindia.com/api/places/nearby/json"
MAPPLS_DISTANCE_URL = "https://apis.mapmyindia.com/advancedmaps/v1/{key}/distance_matrix/driving/{coords}"

# ── Hardcoded Bengaluru fallback ───────────────────────────────────────────
# (NOT a dataset — just 8 well-known junctions for graceful degradation)
_BENGALURU_JUNCTIONS: list[dict] = [
    {"name": "Silk Board Junction",          "lat": 12.9172, "lng": 77.6228},
    {"name": "Marathahalli Bridge",           "lat": 12.9591, "lng": 77.7001},
    {"name": "Koramangala 80 Ft Road",        "lat": 12.9352, "lng": 77.6245},
    {"name": "Hebbal Flyover",                "lat": 13.0358, "lng": 77.5970},
    {"name": "MG Road Metro Station",         "lat": 12.9757, "lng": 77.6073},
    {"name": "Indiranagar 12th Main",         "lat": 12.9784, "lng": 77.6408},
    {"name": "Electronic City Flyover",       "lat": 12.8399, "lng": 77.6770},
    {"name": "Bellandur Junction",            "lat": 12.9255, "lng": 77.6755},
]

_BENGALURU_STATIONS: list[dict] = [
    {"name": "Madiwala Police Station",       "lat": 12.9190, "lng": 77.6230},
    {"name": "Marathahalli Police Station",   "lat": 12.9563, "lng": 77.7012},
    {"name": "HSR Layout Police Station",     "lat": 12.9116, "lng": 77.6474},
    {"name": "Hebbal Police Station",         "lat": 13.0387, "lng": 77.5951},
    {"name": "Cubbon Park Police Station",    "lat": 12.9793, "lng": 77.5963},
    {"name": "Indiranagar Police Station",    "lat": 12.9784, "lng": 77.6388},
]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def _mappls_keys_present() -> bool:
    return bool(MAPMYINDIA_REST_KEY or (MAPMYINDIA_CLIENT_ID and MAPMYINDIA_CLIENT_SECRET))


def _auth_header() -> dict[str, str]:
    """Return the correct Authorization header — static key takes priority over OAuth2."""
    if MAPMYINDIA_REST_KEY:
        return {"Authorization": f"Bearer {MAPMYINDIA_REST_KEY}"}
    # Sync fallback — should not normally be called directly in async code;
    # use _resolve_headers() instead.
    return {}


async def _resolve_headers() -> dict[str, str]:
    """Async: static REST key OR OAuth2 token."""
    if MAPMYINDIA_REST_KEY:
        return {"Authorization": f"Bearer {MAPMYINDIA_REST_KEY}"}
    token = await _get_token()
    return {"Authorization": f"Bearer {token}"}


async def _get_token() -> str:
    """Fetch/refresh Mappls OAuth2 bearer token."""
    global _token, _token_expiry
    if _token and time.time() < _token_expiry - 30:
        return _token
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            MAPPLS_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": MAPMYINDIA_CLIENT_ID,
                "client_secret": MAPMYINDIA_CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data["access_token"]
        _token_expiry = time.time() + int(data.get("expires_in", 3600))
        return _token


async def reverse_geocode(lat: float, lng: float) -> str | None:
    """
    Return a human-readable location name for the given coordinates.

    Primary: real Mappls reverse-geocode API.
    Fallback: nearest entry in the hardcoded Bengaluru junction list.
    """
    if not _mappls_keys_present():
        log.warning(
            "MAPMYINDIA_CLIENT_ID/SECRET not set — using fallback Bengaluru junction "
            "lookup for reverse-geocode (lat=%.4f, lng=%.4f). "
            "Set credentials to use real Mappls API.",
            lat, lng,
        )
        return _fallback_nearest_junction(lat, lng)

    try:
        headers = await _resolve_headers()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://apis.mapmyindia.com/advancedmaps/v1/rev_geocode",
                params={"lat": lat, "lng": lng},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if results:
                r = results[0]
                parts = [
                    r.get("subLocality") or r.get("locality"),
                    r.get("city"),
                    r.get("pincode"),
                ]
                return ", ".join(p for p in parts if p) or r.get("formatted_address")
    except Exception as exc:
        log.error("Mappls reverse-geocode failed: %s — falling back to lookup table", exc)
    return _fallback_nearest_junction(lat, lng)


def _fallback_nearest_junction(lat: float, lng: float) -> str:
    """Return name of nearest hardcoded Bengaluru junction."""
    best = min(_BENGALURU_JUNCTIONS, key=lambda j: _haversine_km(lat, lng, j["lat"], j["lng"]))
    return best["name"]


async def nearest_police_station(lat: float, lng: float) -> dict:
    """
    Return {station_name, distance_km, eta_minutes, route_polyline}.

    Primary: Mappls nearby search + distance-matrix.
    Fallback: nearest entry in the hardcoded station list.
    """
    if not _mappls_keys_present():
        log.warning(
            "MAPMYINDIA_CLIENT_ID/SECRET not set — using fallback station lookup "
            "(lat=%.4f, lng=%.4f). Set credentials for real Mappls routing.",
            lat, lng,
        )
        return _fallback_nearest_station(lat, lng)

    try:
        headers = await _resolve_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            # Step 1: nearby search for police stations
            nearby_resp = await client.get(
                "https://atlas.mapmyindia.com/api/places/nearby/json",
                params={
                    "keywords": "police station",
                    "refLocation": f"{lat},{lng}",
                    "radius": 5000,
                    "sortBy": "dist:asc",
                    "page": 1,
                },
                headers=headers,
            )
            nearby_resp.raise_for_status()
            nearby_data = nearby_resp.json()
            places = nearby_data.get("suggestedLocations", [])
            if not places:
                raise ValueError("No nearby police stations found")
            station = places[0]
            st_lat = float(station["latitude"])
            st_lng = float(station["longitude"])
            st_name = station.get("placeName", "Police Station")

            # Step 2: distance matrix for ETA
            coords_str = f"{lat},{lng};{st_lat},{st_lng}"
            dist_resp = await client.get(
                "https://apis.mapmyindia.com/advancedmaps/v1/distance_matrix/driving/"
                + coords_str,
                headers=headers,
            )
            dist_resp.raise_for_status()
            dist_data = dist_resp.json()
            rows = dist_data.get("results", {}).get("rows", [])
            element = rows[0]["elements"][0] if rows else {}
            distance_m = element.get("distance", 0)
            duration_s = element.get("duration", 0)

            return {
                "station_name": st_name,
                "distance_km": round(distance_m / 1000, 2),
                "eta_minutes": round(duration_s / 60, 1),
                "route_polyline": element.get("polyline"),
            }
    except Exception as exc:
        log.error("Mappls dispatch routing failed: %s — falling back to lookup table", exc)
    return _fallback_nearest_station(lat, lng)


def _fallback_nearest_station(lat: float, lng: float) -> dict:
    """Return nearest hardcoded Bengaluru police station."""
    best = min(_BENGALURU_STATIONS, key=lambda s: _haversine_km(lat, lng, s["lat"], s["lng"]))
    dist = _haversine_km(lat, lng, best["lat"], best["lng"])
    eta = round((dist / 30) * 60, 1)   # rough 30 km/h average
    return {
        "station_name": best["name"],
        "distance_km": round(dist, 2),
        "eta_minutes": eta,
        "route_polyline": None,
    }
