#!/usr/bin/env python3
"""
Hermes Agent Runner
Chạy DeepSeek Harness (V4 Pro) với cấu hình chuyên cho hệ thống giám sát đường sắt.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Load .env
load_dotenv()

try:
    from deepseek_harness import DeepSeekHarness
except ImportError:
    print("❌ Chưa cài deepseek-harness-sdk")
    print("   Chạy: pip install deepseek-harness-sdk")
    sys.exit(1)


# ==================== CẤU HÌNH ====================
BASE_DIR = Path(__file__).parent.resolve()

# Thư mục chứa code Hermes của bạn (OpenCV, IoT scripts...)
WORKSPACE = Path(os.getenv("HERMES_WORKSPACE", BASE_DIR / "examples")).resolve()

# Nơi lưu session log
SESSIONS = Path(os.getenv("HERMES_SESSIONS", BASE_DIR / "sessions")).resolve()
SESSIONS.mkdir(parents=True, exist_ok=True)

# File cấu hình đã được generate (bản plain-list cho Python SDK)
CONFIG = Path(os.getenv(
    "HERMES_CONFIG",
    BASE_DIR / "configs" / "generated-railway-sdk.cordis.yml"
)).resolve()

MODEL = os.getenv("DSH_MODEL", "deepseek-v4-pro")
MAX_TOKENS = int(os.getenv("DSH_MAX_TOKENS", "49152"))


DEFAULT_TASK = """
Hãy kiểm tra script detect_landslide.py và cải thiện nó:

1. Thêm xử lý lỗi tốt hơn khi không đọc được ảnh.
2. Thêm logging rõ ràng (thời gian, thông số).
3. Nếu phát hiện bất thường (is_anomaly=True), hãy mô tả cách gọi tool send_telegram để gửi cảnh báo.
4. Giữ code sạch, dễ đọc, có type hint nếu có thể.
"""


def run_agent(task: str, session_id: str | None = None) -> str:
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("Thiếu DEEPSEEK_API_KEY trong môi trường hoặc file .env")

    if not CONFIG.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file cấu hình: {CONFIG}\n"
            "Hãy chạy: bash generate-config.sh"
        )

    if session_id is None:
        session_id = f"hermes-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"[{datetime.now().isoformat()}] Bắt đầu session: {session_id}")
    print(f"  Model     : {MODEL}")
    print(f"  Workspace : {WORKSPACE}")
    print(f"  Config    : {CONFIG}")
    print("-" * 60)

    with DeepSeekHarness(
        provider="deepseek-official",
        model=MODEL,
        max_tokens=MAX_TOKENS,
        cwd=str(WORKSPACE),
        session_root=str(SESSIONS),
        cordis=str(CONFIG),
    ) as harness:
        result = harness.run(task, session_id=session_id)

    print("-" * 60)
    print(f"[{datetime.now().isoformat()}] Hoàn thành")
    print(result.final_response)
    return result.final_response


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TASK
    try:
        run_agent(task)
    except Exception as e:
        print(f"\n❌ Lỗi: {e}", file=sys.stderr)
        sys.exit(1)
