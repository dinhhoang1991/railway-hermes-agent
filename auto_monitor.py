#!/usr/bin/env python3
"""
Railway Hermes Auto Monitor — vòng cảnh báo tự động 24/7.

Luồng: đọc cảm biến → so ngưỡng → khi vượt ngưỡng: chạy OpenCV detect (nếu
có camera) → gửi cảnh báo Telegram → ghi cảnh báo/kết quả lên dashboard.

Thiết kế DETERMINISTIC (không gọi LLM) cho độ tin cậy + latency thấp; agent
AI vẫn dùng khi cần phân tích chuyên sâu theo lệnh (telegram_bot.py).

Chế độ chạy:
    python auto_monitor.py --once           # kiểm tra 1 lần rồi thoát (dùng với cron)
    python auto_monitor.py --interval 30    # chạy liên tục, lặp mỗi 30 giây

Nguồn dữ liệu: dashboard REST API (dashboard/server.py đã nạp MQTT vào store).
Nếu chưa có dashboard, cần DASHBOARD_URL + dashboard đang chạy.

Cấu hình (.env):
    DASHBOARD_URL          bắt buộc — nguồn dữ liệu cảm biến
    TELEGRAM_BOT_TOKEN     bắt buộc khi muốn gửi cảnh báo
    TELEGRAM_CHAT_ID
    MONITOR_THRESHOLDS     JSON, ví dụ: {"tilt": 8, "vibration": 10, "water": 50}
    MONITOR_COOLDOWN       giây tối thiểu giữa 2 cảnh báo cùng 1 cảm biến (mặc định 300)
    CAMERA_IMAGE           ảnh camera hiện tại (để chạy detect khi vượt ngưỡng)
    CAMERA_REFERENCE       ảnh baseline (để change detection)
    DETECT_SCRIPT          đường dẫn detect_landslide.py (mặc định cạnh script này)
    DETECT_PYTHON          python chạy detect_landslide.py (mặc định "python3")
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent.resolve()
STATE_FILE = BASE / "dashboard" / "data" / "monitor_state.json"
DETECT_SCRIPT_DEFAULT = BASE / "detect_landslide.py"

DEFAULT_THRESHOLDS = {"tilt": 8, "vibration": 10, "water": 50}


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    env_file = BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


ENV = load_env()


# ============================== HTTP / Telegram ==============================

def http_get_json(url: str, timeout: int = 10) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)


def send_telegram(text: str) -> bool:
    token = ENV.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = ENV.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[monitor] Thiếu TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID — bỏ qua gửi Telegram")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        http_post_json(url, {"chat_id": chat_id, "text": text})
        return True
    except urllib.error.HTTPError as exc:
        print(f"[monitor] Gửi Telegram lỗi ({exc.code}): {exc.read().decode()[:200]}")
        return False


# ============================== Nguồn dữ liệu ==============================

def read_sensors() -> list[dict[str, Any]]:
    base = ENV.get("DASHBOARD_URL", "").rstrip("/")
    if not base:
        raise SystemExit("Thiếu DASHBOARD_URL trong .env (cần dashboard đang chạy để lấy dữ liệu cảm biến)")
    try:
        data = http_get_json(f"{base}/api/sensors")
    except (urllib.error.URLError, OSError) as exc:
        print(f"[monitor] Không đọc được dashboard ({exc}) — bỏ qua lượt này")
        return []
    return data.get("sensors", [])


def thresholds() -> dict[str, float]:
    raw = ENV.get("MONITOR_THRESHOLDS", "")
    if not raw:
        return dict(DEFAULT_THRESHOLDS)
    try:
        data = json.loads(raw)
        return {k: float(v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        print("[monitor] MONITOR_THRESHOLDS sai định dạng JSON — dùng mặc định", file=sys.stderr)
        return dict(DEFAULT_THRESHOLDS)


# ============================== Trạng thái (cooldown) ==============================

def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"alerted": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================== OpenCV detect ==============================

def run_detection(image: str | None, reference: str | None) -> dict[str, Any] | None:
    """Chạy detect_landslide.py; trả JSON kết quả hoặc None nếu không cấu hình."""
    if not image:
        return None
    script = Path(ENV.get("DETECT_SCRIPT", str(DETECT_SCRIPT_DEFAULT)))
    if not script.exists():
        print(f"[monitor] Không tìm thấy detect script: {script}")
        return None
    python = ENV.get("DETECT_PYTHON", "python3")
    cmd = [python, str(script), "--image", image]
    if reference:
        cmd += ["--reference", reference]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[monitor] Detect lỗi: {exc}")
        return None
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        print(f"[monitor] Detect trả output không phải JSON: {proc.stdout[:200]}")
        return None


# ============================== Vòng kiểm tra ==============================

def alert_message(sensor: dict[str, Any], thr: float, detection: dict[str, Any] | None) -> str:
    sid = sensor["sensor_id"]
    value = sensor.get("value")
    unit = sensor.get("unit") or ""
    lines = [
        "🚨 CẢNH BÁO ĐƯỜNG SẮT",
        f"Cảm biến {sid} ({sensor.get('type', '?')}): {value} {unit} — vượt ngưỡng {thr} {unit}".rstrip(),
    ]
    if detection:
        lines.append(
            f"OpenCV: {detection.get('severity', '?')} — {detection.get('message', '')}"
        )
    lines.append(f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def post_alert(sensor: dict[str, Any], thr: float, detection: dict[str, Any] | None) -> None:
    base = ENV.get("DASHBOARD_URL", "").rstrip("/")
    if not base:
        return
    try:
        http_post_json(f"{base}/api/alerts", {
            "message": alert_message(sensor, thr, detection),
            "level": "critical",
            "sensor_id": sensor["sensor_id"],
        })
        if detection:
            http_post_json(f"{base}/api/detections", {
                "mode": detection.get("mode", "unknown"),
                "detected": detection.get("detected", False),
                "severity": detection.get("severity", "none"),
                "message": detection.get("message", ""),
            })
    except (urllib.error.URLError, OSError) as exc:
        print(f"[monitor] Ghi dashboard lỗi: {exc}")


def check_once() -> dict[str, Any]:
    """Chạy một lượt kiểm tra; trả thống kê."""
    thrs = thresholds()
    cooldown = int(ENV.get("MONITOR_COOLDOWN", "300"))
    state = load_state()
    alerted = state.setdefault("alerted", {})
    now = time.time()
    result = {"breached": 0, "alerts_sent": 0, "skipped_cooldown": 0}

    for sensor in read_sensors():
        stype = str(sensor.get("type") or "unknown")
        if stype not in thrs:
            continue
        value = float(sensor.get("value") or 0)
        thr = thrs[stype]
        if value <= thr:
            # Hồi phục: nếu trước đó đang trong trạng thái cảnh báo thì xoá để báo mới sau này
            if sensor["sensor_id"] in alerted:
                print(f"[monitor] {sensor['sensor_id']} đã trở lại dưới ngưỡng ({value} <= {thr})")
                del alerted[sensor["sensor_id"]]
            continue

        result["breached"] += 1
        last = alerted.get(sensor["sensor_id"], {})
        if last.get("until", 0) > now:
            result["skipped_cooldown"] += 1
            continue

        detection = run_detection(ENV.get("CAMERA_IMAGE"), ENV.get("CAMERA_REFERENCE"))
        msg = alert_message(sensor, thr, detection)
        print(f"[monitor] ⚠️ {msg.splitlines()[1]}")
        if send_telegram(msg):
            result["alerts_sent"] += 1
        post_alert(sensor, thr, detection)
        alerted[sensor["sensor_id"]] = {"until": now + cooldown}

    save_state(state)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Railway Hermes Auto Monitor")
    parser.add_argument("--interval", type=int, default=30, help="Giây giữa 2 lượt kiểm tra (chế độ liên tục)")
    parser.add_argument("--once", action="store_true", help="Chạy 1 lượt rồi thoát (dùng với cron)")
    args = parser.parse_args()

    print(f"[monitor] Bắt đầu. Ngưỡng: {thresholds()}")

    if args.once:
        result = check_once()
        print(f"[monitor] Xong: {result}")
        return

    print(f"[monitor] Chạy liên tục, kiểm tra mỗi {args.interval}s. Ctrl-C để dừng.")
    while True:
        try:
            result = check_once()
            print(f"[monitor] {time.strftime('%H:%M:%S')} — {result}")
        except KeyboardInterrupt:
            print("\n[monitor] Đã dừng.")
            return
        except Exception as exc:  # noqa: BLE001 - vòng lặp phải sống sót qua lỗi
            print(f"[monitor] Lỗi: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
