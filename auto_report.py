#!/usr/bin/env python3
"""
Railway Hermes Auto Report — báo cáo giám sát định kỳ (hàng ngày/tuần).

Thu thập dữ liệu từ dashboard (cảm biến, cảnh báo, phát hiện) rồi:
- mặc định: dùng AI agent (LLM) tổng hợp thành báo cáo tiếng Việt có cấu trúc;
- `--no-llm`: dùng mẫu cố định (nhanh, không tốn token).

Báo cáo được lưu vào reports/ và (nếu có Telegram) gửi tới chat cảnh báo.

Chạy:
    python auto_report.py --period daily
    python auto_report.py --period weekly --no-llm
    python auto_report.py --period daily --to-telegram   # gửi Telegram

Cấu hình (.env): DASHBOARD_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
HARNESS_DIR (mặc định deepseek-harness cạnh repo).
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telegram_bot import ENV, run_agent, send_message

BASE = Path(__file__).parent.resolve()
REPORTS_DIR = BASE / "reports"

PERIOD_LABEL = {"daily": "Hôm nay", "weekly": "Tuần này"}


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_data() -> dict[str, Any] | None:
    base = ENV.get("DASHBOARD_URL", "").rstrip("/")
    if not base:
        return None
    try:
        sensors = _get_json(f"{base}/api/sensors").get("sensors", [])
        alerts = _get_json(f"{base}/api/alerts?limit=500").get("alerts", [])
        detections = _get_json(f"{base}/api/detections?limit=500").get("detections", [])
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        print(f"[report] Không đọc được dashboard: {exc}")
        return None
    return {"sensors": sensors, "alerts": alerts, "detections": detections}


def _since(items: list[dict[str, Any]], hours: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    for it in items:
        try:
            t = datetime.fromisoformat(it.get("time", "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if t >= cutoff:
            out.append(it)
    return out


def build_digest(data: dict[str, Any], period: str) -> dict[str, Any]:
    hours = 24 if period == "daily" else 168
    alerts = _since(data["alerts"], hours)
    detections = _since(data["detections"], hours)
    return {
        "period": period,
        "sensors": [
            {"sensor_id": s["sensor_id"], "type": s.get("type"), "value": s.get("value"),
             "unit": s.get("unit"), "updated_at": s.get("updated_at")}
            for s in data["sensors"]
        ],
        "alerts_count": len(alerts),
        "alerts": [
            {"time": a.get("time"), "level": a.get("level"), "sensor_id": a.get("sensor_id"),
             "message": a.get("message")}
            for a in alerts[-20:]
        ],
        "detections_count": len(detections),
        "detections": [
            {"time": d.get("time"), "mode": d.get("mode"), "severity": d.get("severity"),
             "message": d.get("message")}
            for d in detections[-20:]
        ],
    }


def template_report(data: dict[str, Any], period: str) -> str:
    """Báo cáo cố định (không LLM)."""
    digest = build_digest(data, period)
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 BÁO CÁO GIÁM SÁT ĐƯỜNG SẮT — {PERIOD_LABEL[period]}",
        f"Thời gian: {now}",
        "",
        f"🔧 Cảm biến online: {len(digest['sensors'])}",
    ]
    for s in digest["sensors"]:
        lines.append(f"  • {s['sensor_id']} ({s['type']}): {s['value']} {s['unit']}")
    lines += [
        "",
        f"⚠️ Cảnh báo trong kỳ: {digest['alerts_count']}",
        f"🔍 Phát hiện bất thường: {digest['detections_count']}",
    ]
    for a in digest["alerts"][-5:]:
        lines.append(f"  - [{a['level']}] {a['sensor_id']}: {a['message'][:70]}")
    if digest["detections_count"] == 0 and digest["alerts_count"] == 0:
        lines.append("\n✅ Không có sự cố bất thường trong kỳ.")
    return "\n".join(lines)


def llm_report(data: dict[str, Any], period: str) -> str:
    """Nhờ agent (LLM) viết báo cáo từ dữ liệu thô."""
    digest = build_digest(data, period)
    prompt = (
        f"Viết báo cáo giám sát đường sắt {PERIOD_LABEL[period]} ngắn gọn, có cấu trúc, "
        "cho lãnh đạo đơn vị. Chỉ dùng dữ liệu JSON dưới đây, nêu rõ: số cảm biến online, "
        "cảnh báo, phát hiện bất thường và kết luận/khuyến nghị. "
        "KHÔNG gửi Telegram, KHÔNG chạy script, chỉ trả nội dung báo cáo.\n\n"
        f"Dữ liệu:\n{json.dumps(digest, ensure_ascii=False, indent=2)}"
    )
    return run_agent(prompt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Railway Hermes Auto Report")
    parser.add_argument("--period", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--no-llm", action="store_true", help="Dùng mẫu cố định thay vì LLM")
    parser.add_argument("--to-telegram", action="store_true", help="Gửi báo cáo qua Telegram")
    parser.add_argument("--out", default=None, help="Ghi báo cáo ra file (mặc định reports/)")
    args = parser.parse_args()

    data = collect_data()
    if data is None:
        print("[report] Không có dữ liệu (thiếu DASHBOARD_URL hoặc dashboard chưa chạy).", flush=True)
        return

    report = template_report(data, args.period) if args.no_llm else llm_report(data, args.period)

    # Lưu file
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M")
    out = Path(args.out) if args.out else REPORTS_DIR / f"report-{args.period}-{stamp}.md"
    out.write_text(report, encoding="utf-8")
    print(f"[report] Đã lưu: {out}")

    if args.to_telegram:
        if send_message(report):
            print("[report] Đã gửi Telegram.")


if __name__ == "__main__":
    main()
