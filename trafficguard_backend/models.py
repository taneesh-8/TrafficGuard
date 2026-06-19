"""Pydantic models — field names must match the frontend contract exactly."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


# ── Sub-objects ────────────────────────────────────────────────────────────

class ViolationItem(BaseModel):
    type: str
    confidence: float
    severity: str          # HIGH | MEDIUM | LOW
    description: str
    bounding_hint: str
    signal_state: Optional[str] = None   # "red"|"yellow"|"green"|null


class VehicleItem(BaseModel):
    type: str
    count: int


class MapPin(BaseModel):
    lat: float
    lng: float
    severity: str
    case_id: str


class ReoffenderInfo(BaseModel):
    plate: str
    offense_count: int
    locations: List[str]
    case_ids: List[str]


# ── Main response ──────────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    case_id: str
    is_new_case: bool
    camera_id: str
    location_name: Optional[str] = None
    plate: Optional[str] = None
    plate_valid: bool
    scene_condition: Optional[str] = None
    violations: List[ViolationItem] = []
    severity: str                       # HIGH | MEDIUM | LOW (or empty for no_violation)
    summary: Optional[str] = None
    status: str                         # auto_challan | pending_review | no_violation
    challan_issued: bool
    review_reason: Optional[str] = None
    pdf_url: Optional[str] = None
    image_url: Optional[str] = None
    map_pin: Optional[MapPin] = None
    reoffender: Optional[ReoffenderInfo] = None


# ── Violation case (GET /violations) ──────────────────────────────────────

class ViolationCase(BaseModel):
    case_id: str
    camera_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_name: Optional[str] = None
    plate: Optional[str] = None
    plate_confidence: Optional[float] = None
    plate_valid: bool = False
    scene_condition: Optional[str] = None
    vehicles: List[VehicleItem] = []
    violations: List[ViolationItem] = []
    severity: Optional[str] = None
    summary: Optional[str] = None
    status: str = "pending_review"
    challan_issued: bool = False
    review_reason: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    frame_count: int = 1
    image_url: Optional[str] = None
    annotated_image_url: Optional[str] = None
    pdf_url: Optional[str] = None


class PaginatedViolations(BaseModel):
    total: int
    page: int
    page_size: int
    results: List[ViolationCase]


# ── Analytics ─────────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    by_violation_type: dict
    by_day: dict
    by_hour: dict
    by_camera: dict
    total_cases: int
    total_challans: int
    total_reoffenders: int


class HeatmapPoint(BaseModel):
    lat: float
    lng: float
    count: int
    severity: str


class ReoffenderRecord(BaseModel):
    plate: str
    offense_count: int
    last_seen: Optional[str]
    locations: List[str]
    case_ids: List[str]
    risk_level: str


class TrendPoint(BaseModel):
    date: str
    count: int


# ── Dispatch ──────────────────────────────────────────────────────────────

class DispatchRequest(BaseModel):
    lat: float
    lng: float
    case_ids: Optional[List[str]] = None


class DispatchResponse(BaseModel):
    station_name: str
    distance_km: float
    eta_minutes: float
    route_polyline: Optional[str] = None
    hotspot_lat: float
    hotspot_lng: float


# ── Camera ────────────────────────────────────────────────────────────────

class CameraRecord(BaseModel):
    camera_id: str
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    trust_score: float
    status: str
    detections_count: int
    false_positive_count: int
