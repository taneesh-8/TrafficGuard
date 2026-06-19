"""
camera_feed_simulator.py

Extracts frames from a LOCAL video file (supplied by the user at runtime)
and POSTs each frame to the TrafficGuard AI /analyze endpoint.

Usage:
    python camera_feed_simulator.py --video path/to/footage.mp4 \\
        --camera-id CAM_047 --fps 1

Arguments:
    --video      Path to a local video file (required, user-supplied)
    --camera-id  Camera ID to send with each frame  (default: CAM_047)
    --fps        Frames to extract per second of video (default: 1)
                 i.e. every (video_fps / fps) real frames is sampled
    --api-url    Backend URL (default: http://localhost:8000)

NOTE: The video file is NOT bundled with this project.
      Provide your own footage at runtime.
"""
from __future__ import annotations
import argparse
import io
import logging
import time

import cv2
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("camera_sim")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TrafficGuard AI camera feed simulator")
    p.add_argument("--video",     required=True, help="Path to local video file")
    p.add_argument("--camera-id", default="CAM_047", help="Camera ID to send with frames")
    p.add_argument("--fps",       type=float, default=1.0,
                   help="Target extraction rate in frames/second (default: 1)")
    p.add_argument("--api-url",   default="http://localhost:8000",
                   help="TrafficGuard AI backend URL")
    return p.parse_args()


def _get_camera_coords(camera_id: str, api_url: str) -> tuple[float | None, float | None]:
    """Fetch known lat/lng for the camera from the /cameras endpoint."""
    try:
        resp = httpx.get(f"{api_url}/cameras", timeout=5)
        resp.raise_for_status()
        for cam in resp.json():
            if cam["camera_id"] == camera_id:
                return cam.get("lat"), cam.get("lng")
    except Exception as exc:
        log.warning("Could not fetch camera coords: %s", exc)
    return None, None


def simulate(video_path: str, camera_id: str, fps: float, api_url: str) -> None:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video file: {video_path}")

    video_fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step   = max(1, int(video_fps / fps))   # sample every N-th frame
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s   = total_frames / video_fps

    log.info(
        "Video: %s | %.1f fps | %d frames (~%.1f s) | sampling every %d frame(s)",
        video_path, video_fps, total_frames, duration_s, frame_step,
    )

    lat, lng = _get_camera_coords(camera_id, api_url)
    if lat:
        log.info("Camera %s coords: %.4f, %.4f", camera_id, lat, lng)
    else:
        log.warning("No coords found for %s — sending without lat/lng", camera_id)

    frame_idx  = 0
    sent       = 0
    interval_s = 1.0 / fps    # time to sleep between sends to avoid flooding

    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        # Encode frame as JPEG
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpeg_bytes = buf.tobytes()

        # POST to /analyze
        files   = {"file": ("frame.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
        data: dict[str, object] = {"camera_id": camera_id}
        if lat is not None:
            data["lat"] = lat
        if lng is not None:
            data["lng"] = lng

        try:
            t0 = time.time()
            resp = httpx.post(f"{api_url}/analyze", files=files, data=data, timeout=60)
            elapsed = time.time() - t0
            if resp.status_code == 200:
                result = resp.json()
                log.info(
                    "Frame %d → case=%s status=%s violations=%d (%.2fs)",
                    frame_idx,
                    result.get("case_id") or "—",
                    result.get("status"),
                    len(result.get("violations") or []),
                    elapsed,
                )
            else:
                log.warning("Frame %d → HTTP %d: %s", frame_idx, resp.status_code, resp.text[:200])
        except Exception as exc:
            log.error("Frame %d → POST failed: %s", frame_idx, exc)

        sent      += 1
        frame_idx += frame_step

        if frame_idx >= total_frames:
            break

        time.sleep(max(0.0, interval_s - (time.time() - t0 if 'elapsed' in dir() else 0)))

    cap.release()
    log.info("Simulation complete. Sent %d frame(s).", sent)


if __name__ == "__main__":
    args = parse_args()
    simulate(args.video, args.camera_id, args.fps, args.api_url)
