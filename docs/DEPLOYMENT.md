# Hướng dẫn triển khai — Railway Hermes Agent

> Hướng dẫn cài đặt, vận hành và kết nối phần cứng cho hệ thống giám sát an toàn
> đường sắt. Xem [Kiến trúc hệ thống](ARCHITECTURE.md) để hiểu tổng quan.

## 1. Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Linux (khuyến nghị Ubuntu 22.04+), macOS |
| Node.js | ≥ 20 (dùng cho DeepSeek Harness) |
| pnpm | phiên bản mới (cài: `npm i -g pnpm`) |
| Python | ≥ 3.10 |
| Mạng | Truy cập internet (gọi API DeepSeek, Telegram) |
| Tài khoản | DeepSeek API Key, Telegram Bot |

## 2. Cài đặt từng bước

```bash
# 1) Clone dự án
git clone https://github.com/dinhhoang1991/railway-hermes-agent.git
cd railway-hermes-agent

# 2) Cài DeepSeek Harness (chỉ 1 lần)
git clone https://github.com/deepseek-ai/deepseek-harness.git
cd deepseek-harness
pnpm install
pnpm run build          # bắt buộc: sinh runtime bundles (nếu thiếu sẽ lỗi typert.host.js)
cd ..

# 3) Môi trường Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install amqtt       # tùy chọn: nạp MQTT cho dashboard/monitor

# 4) Dependency cho tool plugin (mqtt)
cd plugins && npm install && cd ..

# 5) Cấu hình môi trường
cp .env.example .env
# Sửa .env (xem mục 3)

# 6) Sinh config với đường dẫn tuyệt đối
bash generate-config.sh
```

## 3. Biến môi trường (.env)

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ | Khóa API DeepSeek |
| `TELEGRAM_BOT_TOKEN` | ✅ (cảnh báo/bot) | Token bot Telegram |
| `TELEGRAM_CHAT_ID` | ✅ (cảnh báo/bot) | Chat ID nhận cảnh báo (private = số dương) |
| `MQTT_BROKER_URL` | khi dùng MQTT | Ví dụ `mqtt://127.0.0.1:1883` |
| `DASHBOARD_URL` | khi dùng monitor/bot | Ví dụ `http://127.0.0.1:8080` |
| `ALLOWED_USER_IDS` | bot trong group | `"id1,id2"` danh sách user được ra lệnh |
| `MONITOR_THRESHOLDS` | monitor | JSON ngưỡng: `{"tilt": 8, "vibration": 10, "water": 50}` |
| `MONITOR_COOLDOWN` | monitor | Giây giữa 2 cảnh báo cùng cảm biến (mặc định 300) |
| `CAMERA_IMAGE` / `CAMERA_REFERENCE` | auto-detect | Ảnh camera hiện tại / ảnh baseline |
| `DETECT_PYTHON` | auto-detect | Python có OpenCV (mặc định `python3`) |
| `HARNESS_DIR` / `HARNESS_CONFIG` | bot | Đường dẫn harness / config patch |

## 4. Khởi chạy các thành phần

Thứ tự khuyến nghị:

```bash
# 1) MQTT broker (nếu có cảm biến thật). Ví dụ bằng amqtt:
.venv/bin/amqtt            # lắng nghe 0.0.0.0:1883

# 2) Dashboard (nguồn dữ liệu trung tâm)
.venv/bin/python dashboard/server.py --port 8080 --mqtt mqtt://127.0.0.1:1883

# 3) Vòng cảnh báo tự động
.venv/bin/python auto_monitor.py --interval 30

# 4) Telegram bot (ra lệnh từ xa) — tùy chọn
.venv/bin/python telegram_bot.py

# 5) Web UI của agent (chat trực tiếp) — tùy chọn
cd deepseek-harness
pnpm dsh web --patch ../configs/generated-railway.cordis.yml
```

## 5. Vận hành 24/7 (systemd / cron)

### 5.1 Vòng cảnh báo tự động bằng systemd

```bash
sudo cp deploy/railway-hermes-monitor.service /etc/systemd/system/
# Sửa WorkingDirectory + ExecStart cho khớp đường dẫn
sudo systemctl daemon-reload
sudo systemctl enable --now railway-hermes-monitor
systemctl status railway-hermes-monitor
```

### 5.2 Hoặc bằng cron (one-shot mỗi phút)

```bash
crontab -e
* * * * * cd /path/to/railway-hermes-agent && .venv/bin/python auto_monitor.py --once >> monitor.log 2>&1
```

### 5.3 Các dịch vụ khác (nên dùng systemd tương tự)

- Dashboard: `ExecStart=/path/to/.venv/bin/python dashboard/server.py --port 8080 --mqtt mqtt://127.0.0.1:1883`
- Telegram bot: `ExecStart=/path/to/.venv/bin/python telegram_bot.py`

## 6. Kết nối phần cứng (dữ liệu thật)

### 6.1 Cảm biến IoT → MQTT

Thiết bị (ESP32 / Raspberry Pi) publish JSON về topic `railway/sensors/<id>`:

```json
{"sensor_id": "cam-ranh-01", "type": "tilt", "value": 8.5, "unit": "deg"}
```

- `type`: `tilt` (nghiêng), `vibration` (rung), `water` (mực nước) — khớp `MONITOR_THRESHOLDS`.
- Khi publish đúng format, dashboard tự nạp, monitor tự cảnh báo — **không cần sửa code**.

Ví dụ firmware ESP32 + cảm biến MPU6050 (pseudo):

```cpp
// khởi tạo WiFi + MQTT, đọc góc nghiêng từ MPU6050, publish:
String payload = "{\"sensor_id\":\"cam-ranh-01\",\"type\":\"tilt\","
                 "\"value\":" + String(tiltDeg) + ",\"unit\":\"deg\"}";
mqtt.publish("railway/sensors/cam-ranh-01", payload.c_str());
```

### 6.2 Camera → OpenCV

**Cách A — giám sát camera trực tiếp (RTSP):** `detect_landslide.py` đọc trực tiếp
luồng camera, vừa phát hiện chuyển động vừa so baseline định kỳ:

```bash
.venv/bin/python detect_landslide.py \
  --camera rtsp://user:pass@cam-ip:554/stream \
  --duration 60 --baseline-interval 15 --reference baseline.jpg
```

**Cách B — ảnh chụp định kỳ (cho auto_monitor):** đặt trong `.env`:

```env
CAMERA_IMAGE=/path/to/camera/latest.jpg
CAMERA_REFERENCE=/path/to/camera/baseline.jpg
```

- `CAMERA_REFERENCE` chụp khi nền ổn định (không có vật cản).
- Khi cảm biến vượt ngưỡng, monitor chạy `detect_landslide.py --image ... --reference ...` để phát hiện thay đổi (đất đá tràn lấp).

## 7. Kiểm thử nhanh (không cần phần cứng)

```bash
# 1) Test phát hiện chuyển động (video)
.venv/bin/python detect_landslide.py --video test.mp4

# 2) Test phát hiện thay đổi (2 ảnh)
.venv/bin/python detect_landslide.py --image now.jpg --reference baseline.jpg

# 3) Test camera (dùng video file làm nguồn, cùng code path RTSP)
.venv/bin/python detect_landslide.py --camera test.mp4 --duration 5

# 4) Test agent end-to-end (headless)
cd deepseek-harness
pnpm dsh --profile headless --patch ../configs/generated-railway.cordis.yml \
  "Liệt kê các tool bạn có. KHÔNG gửi Telegram."

# 5) Test monitor một lượt
.venv/bin/python auto_monitor.py --once

# 6) Test báo cáo (không LLM)
.venv/bin/python auto_report.py --period daily --no-llm
```

## 8. Kho kiến thức & báo cáo

### 8.1 Kho kiến thức (tra cứu quy trình/lịch bảo trì)

Thư mục `knowledge/` chứa tài liệu Markdown (quy trình kiểm tra ray, lịch bảo trì,
hướng dẫn sử dụng). Agent tự tra cứu khi được hỏi — thêm tài liệu chỉ cần tạo file
`.md`, không sửa code.

### 8.2 Báo cáo định kỳ

```bash
# Chạy thử
.venv/bin/python auto_report.py --period daily --no-llm

# Cài lịch hàng ngày 06:00 (systemd timer)
sudo cp deploy/railway-hermes-report.service deploy/railway-hermes-report.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now railway-hermes-report.timer
```

## 9. Khắc phục sự cố

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| `Cannot find module './prebuilds/linux-x64//pty.node'` | Runtime SDK exe thiếu native module → dùng đường headless (đã build) hoặc cài runtime wheel đúng platform |
| `typert.host.js ... Cannot find module` | Harness chưa build → `cd deepseek-harness && pnpm run build` |
| `service "systemPrompt" has been registered` | Config insert trùng plugin system-prompt → dùng bản `generate-config.sh` mới (patch `update`) |
| Tool không hiện khi liệt kê | Schema tham số sai (`required: false`) hoặc thiếu `mqtt` → `cd plugins && npm install` |
| `ECONNREFUSED 127.0.0.1:1883` | Chưa có MQTT broker (bình thường nếu chưa dùng MQTT) |
| Telegram `401 Unauthorized` | Token bot sai/hết hạn → tạo lại qua @BotFather |
| Telegram `chat not found` | Chat id sai → nhắn `/start` cho bot rồi lấy qua `getUpdates` |
| Dashboard không nhận MQTT | Cần chạy dashboard bằng Python có `amqtt`; kiểm tra `--mqtt` |
| Agent báo `QUOTA: Insufficient Balance` | Tài khoản DeepSeek hết số dư → nạp credit (chỉ ảnh hưởng các tính năng gọi LLM) |
| Gửi PDF cho bot nhưng không trích xuất được văn bản | Thiếu pypdf → `pip install pypdf`; PDF scan không có text |
| Gửi PDF cho bot báo `file is too big` / vượt 20 MB | Nén trước khi gửi: `pip install pymupdf` rồi `python scripts/compress_pdf.py <file.pdf>` |

## 10. Tài liệu liên quan

- [Kiến trúc hệ thống](ARCHITECTURE.md)
- [README](../README.md)
