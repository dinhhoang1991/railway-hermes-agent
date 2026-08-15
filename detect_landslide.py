#!/usr/bin/env python3
"""
Script OpenCV mẫu phát hiện chuyển động / sạt lở đơn giản.
Dùng làm ví dụ để agent gọi qua tool run_opencv_detect.

Cách dùng:
    python detect_landslide.py --image path/to/image.jpg
    python detect_landslide.py --image path/to/image.jpg --threshold 0.3
"""

import argparse
import sys
import json
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    print(json.dumps({
        "status": "error",
        "message": "Thiếu opencv-python. Chạy: pip install opencv-python-headless numpy"
    }, ensure_ascii=False))
    sys.exit(1)


def detect_motion(image_path: str, threshold: float = 0.25) -> dict:
    """Phát hiện chuyển động đơn giản bằng frame difference (demo)."""
    img = cv2.imread(image_path)
    if img is None:
        return {
            "status": "error",
            "message": f"Không đọc được ảnh: {image_path}"
        }

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    # Demo: tính độ tương phản và edge density như proxy cho "bất thường"
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / edges.size

    mean_intensity = float(np.mean(gray))
    std_intensity = float(np.std(gray))

    is_anomaly = edge_density > threshold or std_intensity > 60

    result = {
        "status": "ok",
        "image": str(image_path),
        "edge_density": round(edge_density, 4),
        "mean_intensity": round(mean_intensity, 2),
        "std_intensity": round(std_intensity, 2),
        "threshold": threshold,
        "is_anomaly": bool(is_anomaly),
        "message": "Phát hiện bất thường (demo)" if is_anomaly else "Bình thường (demo)"
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="OpenCV demo phát hiện sạt lở / chuyển động")
    parser.add_argument("--image", required=True, help="Đường dẫn tới ảnh")
    parser.add_argument("--threshold", type=float, default=0.25, help="Ngưỡng edge density")
    parser.add_argument("--save-result", action="store_true", help="Lưu kết quả ra file json")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(json.dumps({
            "status": "error",
            "message": f"File không tồn tại: {args.image}"
        }, ensure_ascii=False))
        sys.exit(1)

    result = detect_motion(str(image_path), threshold=args.threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.save_result:
        out_path = image_path.with_suffix(".result.json")
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã lưu kết quả: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
