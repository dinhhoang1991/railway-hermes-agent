# Railway Hermes Agent + DeepSeek Harness

Agent lập trình thông minh hỗ trợ hệ thống giám sát an toàn đường sắt (Hermes), sử dụng **DeepSeek Harness v0.1** + **DeepSeek-V4-Pro**.

## Tính năng chính

- Coding agent chuyên biệt cho hệ thống đường sắt (OpenCV phát hiện sạt lở / chuyển động, IoT, Telegram)
- Custom tool: `send_telegram` và `run_opencv_detect`
- Python SDK runner có thể chạy thủ công hoặc theo lịch
- System prompt tối ưu cho ngữ cảnh Việt Nam (Cam Ranh - Khánh Hòa)

## Yêu cầu

- Node.js 20+
- Python 3.10+
- DeepSeek API Key
- (Khuyến nghị) Telegram Bot Token + Chat ID

## Cài đặt nhanh

```bash
# 1. Clone repo này
git clone <your-repo-url> railway-hermes-agent
cd railway-hermes-agent

# 2. Cài DeepSeek Harness (một lần)
git clone https://github.com/deepseek-ai/deepseek-harness.git
cd deepseek-harness
pnpm install
pnpm run build
cd ..

# 3. Cài Python SDK
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Cấu hình môi trường
cp .env.example .env
# Sửa file .env với API key thật
```

## Cấu hình đường dẫn tuyệt đối (quan trọng)

DeepSeek Harness yêu cầu đường dẫn tuyệt đối trong file patch.

Chạy script sau để tự động tạo file cấu hình đúng:

```bash
bash scripts/generate-config.sh
```

Script này sẽ tạo:
- `configs/generated-railway.cordis.yml` (đã điền đường dẫn thật)

## Chạy Web UI (dễ debug)

```bash
cd deepseek-harness
pnpm dsh web --patch ../configs/generated-railway.cordis.yml
```

Mở http://127.0.0.1:3080 → chọn model `deepseek-v4-pro`.

## Chạy bằng Python SDK

```bash
source .venv/bin/activate
python hermes_agent_runner.py
```

## Cấu trúc thư mục

```
railway-hermes-agent/
├── configs/
│   └── railway-coding.cordis.yml      # template
├── plugins/
│   ├── cordis.yml
│   └── src/
│       ├── telegram-tool.ts
│       └── opencv-tool.ts
├── examples/
│   └── detect_landslide.py            # script OpenCV mẫu
├── hermes_agent_runner.py
├── requirements.txt
├── .env.example
└── scripts/
    └── generate-config.sh
```

## Biến môi trường (.env)

```env
DEEPSEEK_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-100xxxxxxxxxx
```

## Ghi chú quan trọng

- Đây là phiên bản Developer Preview của DeepSeek Harness → có thể có breaking change.
- Nên chạy agent trong thư mục workspace riêng (không phải production data).
- Tool OpenCV gọi script Python của bạn qua `python3`. Đảm bảo script nhận tham số `--image`.

## Tác giả & Mục đích

Dự án hỗ trợ xây dựng AI Agent giám sát an toàn đường sắt (gác chắn / tuần đường), tích hợp OpenCV + Telegram + IoT.

Nếu bạn là người làm đường sắt và muốn phát triển hệ thống giám sát, repo này là điểm bắt đầu tốt.
