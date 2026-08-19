# Kiến trúc hệ thống — Railway Hermes Agent

> Tài liệu mô tả kiến trúc phần mềm của dự án **Railway Hermes Agent**: nền tảng
> giám sát an toàn đường sắt ứng dụng AI (DeepSeek Harness + DeepSeek-V4-Pro),
> tích hợp IoT (MQTT), thị giác máy tính (OpenCV), cảnh báo Telegram và dashboard
> giám sát. Đối tượng: người phát triển, giảng viên/hội đồng đánh giá đồ án.

## 1. Tổng quan

Hệ thống theo dõi tình trạng an toàn tại khu vực đường sắt (Cam Ranh – Khánh Hòa)
thông qua ba luồng chính:

1. **Thu thập dữ liệu** — cảm biến IoT (độ nghiêng, rung, mực nước) gửi về qua MQTT; camera ghi nhận hình ảnh hiện trường.
2. **Phân tích** — so sánh ngưỡng an toàn; AI agent hiểu yêu cầu bằng tiếng Việt và vận hành các công cụ; OpenCV phát hiện chuyển động/sạt lở.
3. **Phản hồi** — cảnh báo tức thời qua Telegram, hiển thị trên dashboard, người vận hành có thể ra lệnh từ xa.

Toàn bộ phần mềm chạy được độc lập, không yêu cầu dịch vụ đám mây trả phí ngoài API DeepSeek.

## 2. Sơ đồ kiến trúc tổng thể

```
                          Người vận hành
                 ┌─────────────────────────────┐
                 │  Telegram (lệnh + cảnh báo)  │        Web Dashboard (xem)
                 └───────┬──────────────┬──────┘
                         │ lệnh         │ xem
                         ▼              ▼
   ┌──────────────────┐   │    ┌─────────────────────────┐
   │  telegram_bot.py │───┼──▶ │   Dashboard (server.py)  │
   │  (ra lệnh từ xa) │       │   REST API + MQTT ingest  │
   └────────┬─────────┘       └───────▲──────────┬────────┘
            │ chạy agent              │ REST     │ MQTT
            ▼                         │          │
   ┌──────────────────────────────────┼──────────┼──────────────┐
   │               DeepSeek Harness (AI Agent)     │              │
   │  system-prompt (persona đường sắt) + 4 tool plugin          │
   │  ┌──────────────┐ ┌──────────────────┐ ┌──────────┐        │
   │  │ send_telegram│ │ run_opencv_detect│ │ http_*   │        │
   │  └──────────────┘ └────────┬─────────┘ └──────────┘        │
   │                            │ ┌──────────────────────┐      │
   │                            └▶│ mqtt_* (đọc cảm biến)│      │
   │                              └──────────────────────┘      │
   └──────────────────────────────┬─────────────────────────────┘
                                  │ subprocess
                                  ▼
                        ┌────────────────────┐
                        │ detect_landslide.py │  (OpenCV)
                        └────────────────────┘
                                  ▲
                                  │ ảnh
                        ┌────────────────────┐
                        │      Camera        │
                        └────────────────────┘

   ┌────────────────────┐        ┌────────────────────┐
   │   Cảm biến IoT      │──MQTT─▶│    MQTT Broker      │──MQTT─▶ Dashboard
   │ (ESP32 / Raspberry) │        │  (127.0.0.1:1883)   │
   └────────────────────┘        └────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │        auto_monitor.py — vòng cảnh báo tự động 24/7          │
   │  đọc Dashboard → so ngưỡng → gọi detect_landslide.py →      │
   │  gửi Telegram → ghi cảnh báo/detection lên Dashboard         │
   └─────────────────────────────────────────────────────────────┘
```

## 3. Các thành phần

### 3.1 DeepSeek Harness (nền tảng agent)

- Là framework agent plugin-based (Cordis), do `deepseek-ai/deepseek-harness` cung cấp, được clone vào thư mục `deepseek-harness/`.
- Agent chạy với model **DeepSeek-V4-Pro**, nhận system prompt chuyên biệt và tập tool tùy biến.
- Ba cách vận hành agent:
  - **Headless CLI** (chính): `dsh --profile headless --patch <config> "<task>"` — chạy một tác vụ rồi thoát, in kết quả cuối ra stdout. Dùng bởi Telegram bot.
  - **Web UI**: `dsh web --patch <config>` — giao diện chat tại cổng 3080.
  - **Python SDK**: `hermes_agent_runner.py` — gọi runtime đóng gói `dsh-jsonrpc-agent` qua gói `deepseek-harness-sdk`.

### 3.2 System prompt (persona)

- Định nghĩa vai trò: *Senior Software Engineer chuyên hệ thống giám sát an toàn đường sắt Việt Nam, khu vực Cam Ranh – Khánh Hòa*.
- Nêu rõ bộ tool và **quy trình giám sát khuyến nghị** (kiểm tra cảm biến → nếu vượt ngưỡng gửi Telegram → tùy chọn chạy OpenCV).
- Kỹ thuật: patch **cập nhật** entry `system-prompt` có sẵn của profile (không `insert` thêm, vì sẽ xung đột service `systemPrompt`).

### 3.3 Tool plugin (TypeScript, `plugins/src/`)

Mỗi tool là một plugin Cordis, khai báo bằng hàm `defineTool` và đăng ký qua `ctx.tools.register`.

| Tool | Plugin | Vai trò |
|---|---|---|
| `send_telegram` | `telegram-tool.ts` | Gửi tin cảnh báo/thông báo qua Telegram Bot (hỗ trợ HTML) |
| `run_opencv_detect` | `opencv-tool.ts` | Chạy script Python OpenCV qua `child_process`, trả stdout |
| `http_update_sensor_data` / `http_get_sensor_data` / `http_list_sensors` | `iot-http-tool.ts` | Cache cảm biến trong bộ nhớ; tự đồng bộ lên dashboard khi có `DASHBOARD_URL` |
| `mqtt_get_sensor_data` / `mqtt_list_sensors` / `mqtt_check_sensor_threshold` | `iot-mqtt-tool.ts` | Đọc cảm biến real-time qua MQTT (thư viện `mqtt`), kiểm tra ngưỡng |

Lưu ý kỹ thuật quan trọng:
- **Schema tham số** của `defineTool` dùng property-map: field bắt buộc ghi `required: true`, field tùy chọn **bỏ hẳn** `required` (bản harness hiện tại từ chối `required: false`).
- Plugin `mqtt` cần dependency npm (`plugins/package.json` → `cd plugins && npm install`).
- MQTT client được đóng khi plugin dispose (`ctx.effect(() => () => client.end(true))`).

### 3.4 detect_landslide.py (thị giác máy tính)

Script OpenCV thay thế heuristic demo bằng thuật toán thật, 3 chế độ:

| Chế độ | Cơ chế | Dùng cho |
|---|---|---|
| `--video` | Frame differencing (sai khác khung liên tiếp) + ngưỡng + morphology + contour | Camera phát hiện chuyển động |
| `--image + --reference` | So sánh ảnh hiện tại với ảnh baseline → vùng thay đổi | Đất đá tràn lấp, vật thể mới |
| `--image` (đơn) | Chỉ thống kê (edge density, intensity) | Cảnh báo không đủ dữ liệu |

Các tính năng: ROI (giới hạn vùng quan tâm), `--min-area`/`--threshold`/`--blur` tinh chỉnh độ nhạy, `--annotate` ghi ảnh đánh dấu, kết quả JSON có `mode`/`detected`/`severity`/`message`.

### 3.5 Dashboard (`dashboard/server.py` + `static/`)

- Máy chủ HTTP **chỉ dùng thư viện chuẩn Python** (không cần Flask/Django), phục vụ giao diện tĩnh + REST API.
- REST API: `GET/POST /api/sensors`, `/api/alerts`, `/api/detections`, `GET /api/health`.
- Tự nạp dữ liệu MQTT (topic `railway/sensors/#`) nếu cài `amqtt`; không có amqtt thì vẫn chạy qua REST.
- Giao diện (HTML/CSS/JS thuần, không CDN): thẻ cảm biến + sparkline canvas, feed cảnh báo, feed phát hiện, tự làm mới 3 giây.
- Đóng vai trò **kho dữ liệu trung tâm** cho monitor và bot.

### 3.6 Telegram bot (`telegram_bot.py`)

- Long-polling `getUpdates`; nhận lệnh tiếng Việt → chạy agent (headless CLI) → gửi kết quả về lại Telegram.
- Lệnh nhanh: `/help`, `/status` (đọc dashboard REST), `/start`.
- Bảo mật: mặc định chỉ chủ sở hữu (`TELEGRAM_CHAT_ID`) được ra lệnh; group dùng `ALLOWED_USER_IDS`.

### 3.7 Vòng cảnh báo tự động (`auto_monitor.py`)

- **Deterministic** (không gọi LLM) để đạt latency thấp, chi phí thấp, độ tin cậy cao.
- Đọc cảm biến từ dashboard → so ngưỡng theo loại (`MONITOR_THRESHOLDS`) → khi vượt: chạy `detect_landslide.py` (nếu có `CAMERA_IMAGE`/`CAMERA_REFERENCE`) → gửi Telegram → ghi alert/detection lên dashboard.
- **Cooldown** (`MONITOR_COOLDOWN`) chống gửi trùng; trạng thái lưu ở `dashboard/data/monitor_state.json`.
- Hai chế độ: `--once` (cho cron) và `--interval N` (cho systemd).

## 4. Luồng dữ liệu

### 4.1 Luồng thu thập cảm biến (real-time)

```
Cảm biến IoT → (publish MQTT railway/sensors/<id>) → MQTT Broker
    → Dashboard (amqtt ingest) → lưu sensors.json → hiển thị + REST
```

### 4.2 Luồng cảnh báo tự động

```
auto_monitor.py (định kỳ)
    → GET /api/sensors
    → so ngưỡng (value > MONITOR_THRESHOLDS[type])
    → nếu vượt & ngoài cooldown:
         run detect_landslide.py (nếu có camera)
         send Telegram
         POST /api/alerts + /api/detections
```

### 4.3 Luồng ra lệnh từ xa (con người → AI)

```
Người dùng nhắn Telegram → telegram_bot.py → chạy agent (headless)
    → agent dùng tool (mqtt_*/http_*/opencv/send_telegram)
    → trả lời → bot gửi lại Telegram
```

### 4.4 Luồng phát hiện sạt lở (qua AI agent)

```
Lệnh "chạy detect ảnh X" → agent gọi run_opencv_detect
    → subprocess detect_landslide.py --image X [--reference Y]
    → JSON kết quả → agent diễn giải → đề xuất cảnh báo
```

## 5. Mô hình dữ liệu

### 5.1 Tin nhắn MQTT cảm biến

Topic: `railway/sensors/<sensor_id>` — payload JSON:

```json
{"sensor_id": "cam-ranh-01", "type": "tilt", "value": 8.5, "unit": "deg"}
```

### 5.2 Cảm biến (dashboard store)

```json
{
  "sensor_id": "cam-ranh-01",
  "value": 8.5, "type": "tilt", "unit": "deg",
  "updated_at": "2026-08-17T06:00:00+00:00",
  "history": [{"t": "...", "v": 8.5}, "…"]
}
```

### 5.3 Cảnh báo / phát hiện

```json
{"id": "a1b2c3d4", "time": "…", "level": "critical", "message": "…", "sensor_id": "cam-ranh-01"}
{"id": "e5f6a7b8", "time": "…", "mode": "change_detection", "detected": true, "severity": "high", "message": "…"}
```

## 6. Công nghệ sử dụng

| Lớp | Công nghệ |
|---|---|
| AI agent | DeepSeek Harness (Cordis, TypeScript), DeepSeek-V4-Pro |
| Ngôn ngữ | TypeScript (plugin/tool), Python 3.10+ (script, bot, monitor, dashboard) |
| Thị giác máy tính | OpenCV (`opencv-python-headless`), NumPy |
| IoT / messaging | MQTT (`mqtt` npm cho tool, `amqtt` cho dashboard/monitor) |
| Giao diện | HTML + CSS + JavaScript thuần (dashboard), Web UI của Harness (3080) |
| Thông báo | Telegram Bot API |
| Lưu trữ | JSON file (dashboard), JSONL session (harness) |
| Vận hành | cron / systemd |

## 7. Quyết định thiết kế

| Quyết định | Lý do |
|---|---|
| Vòng cảnh báo **không gọi LLM** (deterministic) | latency thấp (giây, không phải phút), không tốn token 24/7, không phụ thuộc model; AI chỉ dùng khi có lệnh |
| Tách **2 định dạng config** (patch-list vs plain-list) | `dsh --patch` cần patch-list (overlay lên profile); runtime SDK cần plain entry-list (thay toàn bộ config) |
| Dashboard là **kho dữ liệu trung tâm** | một nguồn duy nhất cho monitor, bot, UI; MQTT ingest tập trung |
| **Cooldown** cảnh báo | tránh bùng nổ tin khi cảm biến nhiễu/dao động quanh ngưỡng |
| Tool schema **bỏ `required: false`** | khớp ràng buộc của `defineTool` phiên bản hiện tại |
| Bot/telegram dùng **thư viện chuẩn Python** | không phụ thuộc framework, dễ triển khai |

## 8. Bảo mật

- Telegram bot chỉ nhận lệnh từ chủ sở hữu (`TELEGRAM_CHAT_ID`) hoặc danh sách `ALLOWED_USER_IDS`.
- Dashboard mặc định bind `127.0.0.1` — chỉ mở `0.0.0.0` khi có lớp bảo vệ (reverse proxy + xác thực).
- Không commit secret: `.env` nằm trong `.gitignore`.
- `DEEPSEEK_API_KEY`, `TELEGRAM_BOT_TOKEN` đọc từ môi trường/`.env`, không hardcode.

## 9. Hạn chế hiện tại & hướng phát triển

| Hạn chế | Hướng khắc phục |
|---|---|
| Dữ liệu cảm biến/camera đang là giả lập (chưa có phần cứng thật) | Kết nối ESP32 + cảm biến MPU6050 publish MQTT; camera thật + baseline |
| Dashboard lưu JSON bộ nhớ (giới hạn lịch sử) | Chuyển sang SQLite để lưu lịch sử dài hạn + biểu đồ |
| Chưa có xác thực dashboard | Thêm reverse proxy + token |
| Python SDK runner phụ thuộc native module runtime | Dùng đường headless (đã ổn định) hoặc cài runtime wheel đúng platform |
| Thuật toán phát hiện chưa hiệu chỉnh với dữ liệu thật | Thu thập ảnh thực, tune ngưỡng, cân nhắc MOG2/ML |
| Bot chạy agent mới mỗi lệnh (không nhớ ngữ cảnh) | Duy trì session agent tái sử dụng qua JSON-RPC |

## 10. Cấu trúc thư mục

Xem [README](../README.md#cấu-trúc-thư-mục).

## 11. Tài liệu liên quan

- [Hướng dẫn triển khai](DEPLOYMENT.md)
- [README](../README.md)
