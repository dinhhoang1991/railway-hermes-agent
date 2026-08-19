# Kho kiến thức đường sắt (knowledge base)

Thư mục này chứa **quy trình, lịch bảo trì và tài liệu hướng dẫn** để AI agent
(Railway Hermes) tra cứu khi người lao động hỏi bằng tiếng Việt tự nhiên qua
Telegram, ví dụ:

- *"Quy trình kiểm tra ray đoạn km 1.245 đến 1.250?"*
- *"Lịch bảo trì tuần này của tổ 3?"*
- *"Hướng dẫn sử dụng thiết bị đo nghiêng?"*

## Cách thêm tài liệu mới

1. Tạo file Markdown (`.md`) trong thư mục này, đặt tên rõ nghĩa.
2. Ghi nội dung theo cấu trúc có tiêu đề (`##`) để agent dễ đọc.
3. Không cần sửa code — agent dùng công cụ `read`/`grep`/`glob` để tìm nội dung.

## Các file hiện có

| File | Nội dung |
|---|---|
| `quy-trinh-kiem-tra-ray.md` | Quy trình kiểm tra ray, tà vẹt, nền đường |
| `lich-bao-tri.md` | Lịch bảo trì định kỳ mẫu theo tổ/khu đoạn |
| `huong-dan-su-dung.md` | Hướng dẫn người lao động dùng hệ thống Hermes |

> **Lưu ý:** dữ liệu trong các file này là **mẫu minh họa** — hãy thay bằng quy
> trình/lịch thực tế của đơn vị trước khi đưa vào vận hành.
