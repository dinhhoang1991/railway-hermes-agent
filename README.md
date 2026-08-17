# Railway Hermes Agent + DeepSeek Harness

Agent lập trình thông minh hỗ trợ hệ thống giám sát an toàn đường sắt (Hermes), sử dụng **DeepSeek Harness** + **DeepSeek-V4-Pro**.

## Tính năng chính

- Coding agent chuyên biệt cho hệ thống đường sắt (OpenCV phát hiện sạt lở / chuyển động, IoT, Telegram)
- Custom tool: `send_telegram`, `run_opencv_detect`, `http_*` (cache cảm biến), `mqtt_*` (cảm biến real-time)
- Python SDK runner chạy thủ công hoặc theo lịch
- System prompt tối ưu cho ngữ cảnh Việt Nam (Cam Ranh - Khánh Hòa)

## Yêu cầu

- Node.js 20+
- Python 3.10+
- DeepSeek API Key
- (Khuyến nghị) Telegram Bot Token + Chat ID
- (Tùy chọn) MQTT broker cho dữ liệu cảm biến real-time

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

# 4. Cài dependency cho tool plugin (mqtt cho iot-mqtt-tool)
cd plugins && npm install && cd ..

# 5. Cấu hình môi trường
cp .env.example .env
# Sửa file .env với API key thật
```

## Cấu hình đường dẫn tuyệt đối (quan trọng)

DeepSeek Harness yêu cầu đường dẫn tuyệt đối trong file patch (overlay) để tìm được các tool plugin.

Chạy script sau để tự động tạo file cấu hình đã điền đường dẫn thật:

```bash
bash generate-config.sh
```

Script này kiểm tra 4 file tool trong `plugins/src/` rồi tạo 2 file config:

- `configs/generated-railway.cordis.yml` — **patch-list** cho `dsh web --patch` / `dsh --profile headless --patch`
- `configs/generated-railway-sdk.cordis.yml` — **plain entry list** cho Python SDK runner (`cordis=...`)

## Các tool

| Tool | File plugin | Chức năng |
| --- | --- | --- |
| `send_telegram` | `plugins/src/telegram-tool.ts` | Gửi cảnh báo/thông báo qua Telegram (hỗ trợ HTML) |
| `run_opencv_detect` | `plugins/src/opencv-tool.ts` | Chạy script Python OpenCV phát hiện sạt lở / chuyển động |
| `http_update_sensor_data` / `http_get_sensor_data` / `http_list_sensors` | `plugins/src/iot-http-tool.ts` | Cache cảm biến trong bộ nhớ (nạp thủ công khi chưa có MQTT) |
| `mqtt_get_sensor_data` / `mqtt_list_sensors` / `mqtt_check_sensor_threshold` | `plugins/src/iot-mqtt-tool.ts` | Đọc cảm biến real-time qua MQTT + kiểm tra ngưỡng |

## Chạy Web UI (dễ debug)

```bash
# Sinh config đã điền đường dẫn thật (nếu chưa chạy)
bash generate-config.sh

cd deepseek-harness
pnpm dsh web --patch ../configs/generated-railway.cordis.yml
```

Mở http://127.0.0.1:3080 → chọn model `deepseek-v4-pro`.

Để kiểm tra end-to-end, bạn có thể hỏi agent: *"Hãy liệt kê các cảm biến đang online"* (gọi `mqtt_list_sensors`), hoặc *"Cập nhật cảm biến cam-ranh-01 độ nghiêng 12 độ rồi kiểm tra có vượt ngưỡng không"* (gọi `http_update_sensor_data` + `mqtt_check_sensor_threshold`).

## Chạy bằng Python SDK

```bash
source .venv/bin/activate
python hermes_agent_runner.py "Nhiệm vụ của bạn"
```

Runner dùng `configs/generated-railway-sdk.cordis.yml` (đã được `generate-config.sh` sinh), cấu hình plain-list cho runtime bundled `dsh-jsonrpc-agent`. Không truyền tham số thì runner dùng task mặc định (cải thiện `detect_landslide.py`).

## Cấu trúc thư mục

```
railway-hermes-agent/
├── configs/
│   ├── railway-coding.cordis.yml          # template config (system prompt + đăng ký tool)
│   └── generated-railway*.cordis.yml      # sinh bởi generate-config.sh (gitignored)
├── plugins/
│   ├── package.json                       # dependency mqtt cho tool plugin
│   └── src/
│       ├── telegram-tool.ts
│       ├── opencv-tool.ts
│       ├── iot-http-tool.ts
│       └── iot-mqtt-tool.ts
├── detect_landslide.py                # script OpenCV mẫu
├── hermes_agent_runner.py             # Python SDK runner
├── generate-config.sh                 # sinh configs/generated-railway*.cordis.yml
├── requirements.txt
└── .env.example
```

## Biến môi trường (.env)

```env
DEEPSEEK_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-100xxxxxxxxxx
MQTT_BROKER_URL=mqtt://127.0.0.1:1883
# MQTT_USERNAME=
# MQTT_PASSWORD=
```

Tool MQTT subscribe topic `railway/sensors/#`; mỗi message gửi lên là JSON có ít nhất `sensor_id` và `value`, ví dụ:

```json
{"sensor_id": "cam-ranh-01", "type": "tilt", "value": 8.5, "unit": "deg"}
```

## Ghi chú quan trọng

- Đây là phiên bản Developer Preview của DeepSeek Harness → có thể có breaking change.
- Nên chạy agent trong thư mục workspace riêng (không phải production data).
- Tool OpenCV gọi script Python của bạn qua `python3`. Đảm bảo script nhận tham số `--image`.
- Tool plugin cần dependency npm: chạy `cd plugins && npm install` (hiện chỉ cần `mqtt`).
- Python SDK runner dùng runtime bundled `dsh-jsonrpc-agent` (gói `deepseek-harness-runtime-bin`). Runtime này cần native modules (node-pty) đúng platform; nếu boot báo lỗi native module, hãy cài bản runtime wheel khớp platform của máy, hoặc chạy qua giao diện Web/headless (đường dẫn source đã `pnpm run build`).
- `configs/railway-coding.cordis.yml` là template; đừng chỉnh trực tiếp `configs/generated-railway*.cordis.yml` vì `generate-config.sh` sẽ ghi đè.

## Tác giả & Mục đích

Dự án hỗ trợ xây dựng AI Agent giám sát an toàn đường sắt (gác chắn / tuần đường), tích hợp OpenCV + Telegram + IoT.

Nếu bạn là người làm đường sắt và muốn phát triển hệ thống giám sát, repo này là điểm bắt đầu tốt.
