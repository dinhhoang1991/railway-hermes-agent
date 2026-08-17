#!/usr/bin/env python3
"""
Railway Hermes Telegram Bot — ra lệnh qua Telegram và nhận trả lời.

Bạn nhắn lệnh tiếng Việt tự nhiên cho bot (ví dụ: "kiểm tra cảm biến",
"chạy detect ảnh này..."), bot chạy agent Railway Hermes rồi gửi kết quả
về lại Telegram.

Cấu hình (.env):
    TELEGRAM_BOT_TOKEN           bắt buộc
    TELEGRAM_CHAT_ID             chủ sở hữu mặc định (private chat)
    ALLOWED_USER_IDS             tùy chọn: "id1,id2" danh sách user được phép
                                 (bắt buộc khi bot trong group)
    HARNESS_DIR                  tùy chọn: thư mục deepseek-harness
    HARNESS_CONFIG               tùy chọn: config patch (mặc định
                                 configs/generated-railway.cordis.yml)
    BOT_POLL_INTERVAL            giây giữa 2 lần hỏi update (mặc định 2)

Lệnh nhanh (không cần agent):
    /help      hướng dẫn
    /status    trạng thái cảm biến (đọc từ dashboard REST API nếu có
               DASHBOARD_URL, ngược lại từ agent)

Chạy:
    python telegram_bot.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent.resolve()
HARNESS_DIR = Path(os.getenv("HARNESS_DIR", BASE / "deepseek-harness")).resolve()
CONFIG = Path(os.getenv("HARNESS_CONFIG", BASE / "configs" / "generated-railway.cordis.yml")).resolve()
POLL_INTERVAL = float(os.getenv("BOT_POLL_INTERVAL", "2"))
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "600"))
MAX_REPLY = 4000  # Telegram giới hạn 4096 ký tự/tin


def load_env() -> tuple[dict[str, str], dict[str, str]]:
    """Nạp .env (chỉ thư viện chuẩn).

    Trả (env_merged, env_file): env_merged = os.environ + .env (không ghi đè);
    env_file chỉ chứa giá trị từ file .env (để quyết định các biến "cấu hình"
    như DSH_HOME không bị ảnh hưởng bởi môi trường bên ngoài).
    """
    env_merged = dict(os.environ)
    env_file: dict[str, str] = {}
    env_file_path = BASE / ".env"
    if env_file_path.exists():
        for line in env_file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            env_file.setdefault(key, value)
            env_merged.setdefault(key, value)
    return env_merged, env_file


ENV, ENV_FILE = load_env()
TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = (ENV.get("TELEGRAM_CHAT_ID") or "").strip()
ALLOWED = {u.strip() for u in ENV.get("ALLOWED_USER_IDS", "").split(",") if u.strip()}


# ============================== Telegram API ==============================

def tg_call(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TOKEN:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN trong .env")
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_message(chat_id: int, text: str) -> None:
    for chunk in split_text(text):
        try:
            tg_call("sendMessage", {"chat_id": chat_id, "text": chunk})
        except urllib.error.HTTPError as exc:
            print(f"[bot] Gửi tin thất bại ({exc.code}): {exc.read().decode()[:200]}")


def split_text(text: str, size: int = MAX_REPLY) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else ["(trống)"]
    chunks: list[str] = []
    while text:
        chunks.append(text[:size])
        text = text[size:]
    return chunks


# ============================== Agent ==============================

def extract_response(stdout: str) -> str:
    """Bỏ các dòng log đầu (dạng [XXX] ...) giữ lại phần trả lời của agent."""
    lines = stdout.splitlines()
    start = 0
    while start < len(lines) and re.match(r"^\s*\[[^\]]+\]", lines[start]):
        start += 1
    return "\n".join(lines[start:]).strip()


def run_agent(task: str) -> str:
    """Chạy agent qua headless CLI (source). Trả nội dung trả lời hoặc lỗi."""
    if not HARNESS_DIR.joinpath("apps/cli/src/bin.ts").exists():
        return f"❌ Không tìm thấy harness tại {HARNESS_DIR} (chưa clone? thiếu build?)"
    if not CONFIG.exists():
        return f"❌ Thiếu config {CONFIG} — hãy chạy: bash generate-config.sh"

    cmd = [
        "node", "--import", "tsx/esm",
        str(HARNESS_DIR / "apps/cli/src/bin.ts"),
        "--profile", "headless",
        "--patch", str(CONFIG),
        task,
    ]
    env = os.environ.copy()
    # DSH_HOME chỉ lấy từ .env (cấu hình tường minh); mặc định dùng thư mục
    # repo-local ghi được — không kế thừa DSH_HOME của môi trường bên ngoài.
    env["DSH_HOME"] = ENV_FILE.get("DSH_HOME") or str(BASE / "sessions" / "dsh-home")
    env.setdefault("DEEPSEEK_API_KEY", ENV.get("DEEPSEEK_API_KEY", ""))
    env.setdefault("DASHBOARD_URL", ENV.get("DASHBOARD_URL", ""))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=AGENT_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return f"❌ Agent chạy quá {AGENT_TIMEOUT}s — thử lệnh ngắn hơn."
    except FileNotFoundError:
        return "❌ Không tìm thấy 'node' trong PATH."

    reply = extract_response(proc.stdout)
    if not reply and proc.returncode != 0:
        reply = f"❌ Agent lỗi (exit {proc.returncode}):\n{(proc.stderr or '').strip()[-1500:]}"
    if not reply:
        reply = f"❌ Agent không trả lời (exit {proc.returncode})."
    return reply


# ============================== Xử lý lệnh ==============================

def dashboard_status() -> str:
    """Đọc trạng thái cảm biến từ dashboard REST API."""
    base = ENV.get("DASHBOARD_URL", "")
    if not base:
        return ""
    try:
        with urllib.request.urlopen(f"{base}/api/sensors", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - dashboard tuỳ chọn
        return f"(dashboard không khả dụng: {exc})"
    sensors = data.get("sensors", [])
    if not sensors:
        return "Chưa có dữ liệu cảm biến."
    lines = []
    for s in sensors:
        lines.append(f"• {s['sensor_id']} ({s.get('type', '?')}): {s['value']} {s.get('unit', '')} — cập nhật {s.get('updated_at', '?')}")
    return "📡 Cảm biến:\n" + "\n".join(lines)


def is_authorized(user_id: int) -> bool:
    if ALLOWED:
        return str(user_id) in ALLOWED
    # Mặc định: chủ sở hữu (TELEGRAM_CHAT_ID). Private chat: chat_id == user_id.
    return OWNER_ID.isdigit() and str(user_id) == OWNER_ID


def handle_message(chat_id: int, user_id: int, text: str) -> str:
    if not is_authorized(user_id):
        return "⛔ Bạn không có quyền ra lệnh cho bot này."
    text = text.strip()
    low = text.lower()
    if text.startswith(("/help", "/start")) or low in ("help", "start", "giúp", "trợ giúp"):
        return (
            "🤖 Railway Hermes Bot — ra lệnh bằng tiếng Việt tự nhiên:\n"
            "• \"kiểm tra cảm biến\" — agent liệt kê cảm biến MQTT\n"
            "• \"cập nhật cảm biến cam-ranh-01 độ nghiêng 12 độ\" — ghi vào cache\n"
            "• \"chạy detect ảnh <đường dẫn>\" — chạy OpenCV detect\n"
            "• \"/status\" — trạng thái cảm biến nhanh (không cần agent)\n"
            "• \"/help\" — hướng dẫn này"
        )
    if text.startswith("/status"):
        status = dashboard_status()
        if status:
            return status
        return "⚠️ Chưa cấu hình DASHBOARD_URL — để /status dùng agent: " + run_agent("Hãy liệt kê các cảm biến đang online.")
    return run_agent(text)


def poll_loop() -> None:
    offset = 0
    print("[bot] Railway Hermes Bot đang chạy. Chờ lệnh Telegram...")
    while True:
        try:
            updates = tg_call("getUpdates", {"offset": offset, "timeout": 20})
        except Exception as exc:  # noqa: BLE001 - giữ bot sống qua lỗi mạng
            print(f"[bot] Lỗi getUpdates: {exc}")
            time.sleep(POLL_INTERVAL)
            continue
        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            chat_id = (message.get("chat") or {}).get("id")
            user_id = (message.get("from") or {}).get("id")
            if not text or chat_id is None or user_id is None:
                continue
            print(f"[bot] Lệnh từ {user_id}: {text[:80]}")
            send_message(chat_id, "⏳ Đang xử lý, chờ chút...")
            reply = handle_message(chat_id, user_id, text)
            send_message(chat_id, reply)
            print(f"[bot] Đã trả lời {len(reply)} ký tự.")


def main() -> None:
    if not TOKEN:
        print("❌ Thiếu TELEGRAM_BOT_TOKEN trong .env", file=sys.stderr)
        sys.exit(1)
    # Kiểm tra token hợp lệ
    try:
        me = tg_call("getMe")
    except urllib.error.HTTPError:
        print("❌ Token bot không hợp lệ.", file=sys.stderr)
        sys.exit(1)
    print(f"[bot] Bot @{me['result'].get('username')} — sẵn sàng.")
    poll_loop()


if __name__ == "__main__":
    main()
