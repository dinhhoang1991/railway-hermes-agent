#!/usr/bin/env python3
"""
Dashboard giám sát an toàn đường sắt (Railway Hermes Dashboard).

Máy chủ HTTP đơn giản (chỉ dùng thư viện chuẩn) phục vụ:
- Giao diện dashboard tĩnh (static/)
- REST API cho cảm biến / cảnh báo / kết quả phát hiện
- Tự nạp dữ liệu cảm biến từ MQTT (topic railway/sensors/#) nếu có amqtt

Chạy:
    python dashboard/server.py --port 8080
    python dashboard/server.py --port 8080 --mqtt mqtt://127.0.0.1:1883

API:
    GET  /api/health
    GET  /api/sensors                    danh sách cảm biến (mới nhất trước)
    POST /api/sensors                    {sensor_id, value, type?, unit?, extra?}
    GET  /api/alerts?limit=N             lịch sử cảnh báo
    POST /api/alerts                     {message, level?, sensor_id?}
    GET  /api/detections?limit=N         kết quả phát hiện (OpenCV...)
    POST /api/detections                 {mode?, detected, severity?, message?, image?}
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent.resolve()
STATIC = BASE / "static"
DATA = BASE / "data"
SENSORS_FILE = DATA / "sensors.json"
ALERTS_FILE = DATA / "alerts.json"
DETECTIONS_FILE = DATA / "detections.json"

SENSOR_HISTORY_LIMIT = 120
ALERT_LIMIT = 100
DETECTION_LIMIT = 50


# ============================== Lưu trữ ==============================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_sensors() -> dict[str, dict[str, Any]]:
    return _read_json(SENSORS_FILE, {})


def _load_alerts() -> list[dict[str, Any]]:
    return _read_json(ALERTS_FILE, [])


def _load_detections() -> list[dict[str, Any]]:
    return _read_json(DETECTIONS_FILE, [])


def update_sensor(payload: dict[str, Any]) -> dict[str, Any]:
    """Ghi/nạp một lần đo cảm biến; giữ lịch sử gần nhất để vẽ sparkline."""
    sensor_id = str(payload.get("sensor_id", "")).strip()
    if not sensor_id:
        raise ValueError("sensor_id là bắt buộc")
    try:
        value = float(payload["value"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("value phải là số")

    sensors = _load_sensors()
    now = _now_iso()
    prev = sensors.get(sensor_id, {})
    history = list(prev.get("history", []))
    history.append({"t": now, "v": value})
    if len(history) > SENSOR_HISTORY_LIMIT:
        history = history[-SENSOR_HISTORY_LIMIT:]

    sensors[sensor_id] = {
        "sensor_id": sensor_id,
        "value": value,
        "type": payload.get("type") or prev.get("type") or "unknown",
        "unit": payload.get("unit") or prev.get("unit") or "",
        "extra": payload.get("extra") or prev.get("extra") or {},
        "updated_at": now,
        "history": history,
    }
    _write_json(SENSORS_FILE, sensors)
    return sensors[sensor_id]


def add_alert(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ValueError("message là bắt buộc")
    alerts = _load_alerts()
    alert = {
        "id": uuid.uuid4().hex[:8],
        "time": _now_iso(),
        "level": payload.get("level") or "warning",
        "message": message,
        "sensor_id": payload.get("sensor_id") or None,
    }
    alerts.append(alert)
    _write_json(ALERTS_FILE, alerts[-ALERT_LIMIT:])
    return alert


def add_detection(payload: dict[str, Any]) -> dict[str, Any]:
    detections = _load_detections()
    detection = {
        "id": uuid.uuid4().hex[:8],
        "time": _now_iso(),
        "mode": payload.get("mode") or "unknown",
        "detected": bool(payload.get("detected", False)),
        "severity": payload.get("severity") or "none",
        "message": payload.get("message") or "",
        "image": payload.get("image") or None,
    }
    detections.append(detection)
    _write_json(DETECTIONS_FILE, detections[-DETECTION_LIMIT:])
    return detection


# ============================== MQTT ==============================

def _mqtt_worker(broker_url: str) -> None:
    """Nạp cảm biến từ MQTT (railway/sensors/#) vào store. Chạy nền."""
    try:
        import asyncio
        from amqtt.client import MQTTClient
    except ImportError:
        print("[dashboard] Không có amqtt — bỏ qua nạp MQTT (dashboard vẫn chạy qua REST API)")
        return

    async def run() -> None:
        client = MQTTClient(client_id="dashboard-ingest")
        await client.connect(broker_url)
        await client.subscribe([("railway/sensors/#", 0)])
        print(f"[dashboard] MQTT ingest sẵn sàng: {broker_url}")
        while True:
            try:
                message = await client.deliver_message(timeout_duration=5.0)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001 - worker nền
                print(f"[dashboard] Lỗi MQTT: {exc}")
                break
            topic = str(message.topic)
            try:
                data = json.loads(message.data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                print(f"[dashboard] Bỏ qua message không phải JSON: {topic}")
                continue
            try:
                update_sensor({
                    "sensor_id": data.get("sensor_id") or topic.rsplit("/", 1)[-1],
                    "value": data.get("value"),
                    "type": data.get("type"),
                    "unit": data.get("unit"),
                    "extra": data,
                })
            except ValueError as exc:
                print(f"[dashboard] Bỏ qua message lỗi: {exc}")

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - worker nền, log là đủ
        print(f"[dashboard] Lỗi MQTT worker: {exc}")


def start_mqtt_worker(broker_url: str | None) -> None:
    url = broker_url or os.getenv("MQTT_BROKER_URL") or "mqtt://127.0.0.1:1883"
    thread = threading.Thread(target=_mqtt_worker, args=(url,), daemon=True)
    thread.start()
    print(f"[dashboard] Đang nạp MQTT từ {url} (topic railway/sensors/#)")


# ============================== HTTP ==============================

class Handler(BaseHTTPRequestHandler):
    server_version = "RailwayHermesDashboard/1.0"

    # -- tiện ích -----------------------------------------------------
    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[dashboard] {self.address_string()} {fmt % args}")

    # -- routes -------------------------------------------------------
    def _route_api(self) -> None:
        path = self.path.split("?", 1)[0]
        if self.command == "GET" and path == "/api/health":
            self._json({"status": "ok", "time": _now_iso()})
            return
        if path == "/api/sensors":
            if self.command == "GET":
                sensors = sorted(
                    _load_sensors().values(),
                    key=lambda s: s.get("updated_at", ""),
                    reverse=True,
                )
                self._json({"sensors": sensors})
                return
            if self.command == "POST":
                try:
                    sensor = update_sensor(self._read_body())
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                self._json({"ok": True, "sensor": sensor}, 201)
                return
        if path == "/api/alerts":
            if self.command == "GET":
                limit = int(self.path.split("limit=")[-1]) if "limit=" in self.path else 20
                self._json({"alerts": _load_alerts()[-limit:]})
                return
            if self.command == "POST":
                try:
                    alert = add_alert(self._read_body())
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                self._json({"ok": True, "alert": alert}, 201)
                return
        if path == "/api/detections":
            if self.command == "GET":
                limit = int(self.path.split("limit=")[-1]) if "limit=" in self.path else 20
                self._json({"detections": _load_detections()[-limit:]})
                return
            if self.command == "POST":
                try:
                    detection = add_detection(self._read_body())
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                self._json({"ok": True, "detection": detection}, 201)
                return
        self._json({"error": "Not found"}, 404)

    def _route_static(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC)) or not target.is_file():
            self._json({"error": "Not found"}, 404)
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".json": "application/json; charset=utf-8",
        }
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._route_api()
        else:
            self._route_static()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._route_api()
        else:
            self._json({"error": "Not found"}, 404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Railway Hermes Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Cổng HTTP (mặc định 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Địa chỉ bind (mặc định 127.0.0.1)")
    parser.add_argument("--mqtt", default=None, help="MQTT broker URL, ví dụ mqtt://127.0.0.1:1883")
    args = parser.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    for f in (SENSORS_FILE, ALERTS_FILE, DETECTIONS_FILE):
        if not f.exists():
            _write_json(f, {} if f is SENSORS_FILE else [])

    start_mqtt_worker(args.mqtt)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[dashboard] Railway Hermes Dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] Đã dừng.")


if __name__ == "__main__":
    main()
