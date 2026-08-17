#!/usr/bin/env python3
"""
Phát hiện chuyển động / sạt lở cho giám sát an toàn đường sắt.

Cung cấp 3 chế độ phát hiện thật (không còn là heuristic demo):

1. video motion     — phát hiện chuyển động thật bằng frame differencing
                      (sai khác giữa các khung hình liên tiếp) + contour.
   ``python detect_landslide.py --video path/to/cam.mp4``

2. change detection — phát hiện thay đổi so với ảnh tham chiếu (đất/đá tràn
                      lấp, vật thể mới xuất hiện trên khu vực quan sát).
   ``python detect_landslide.py --image now.jpg --reference baseline.jpg``

3. single image     — ảnh đơn chỉ trả về thống kê; KHÔNG đủ để kết luận
                      chuyển động. Dùng khi chưa có nguồn video/ảnh tham chiếu.
   ``python detect_landslide.py --image path/to/image.jpg``

Tham số chính:
    --threshold  ngưỡng sai khác xám (0-255); càng nhỏ càng nhạy (mặc định 25)
    --min-area   diện tích contour tối thiểu (px) để tính là chuyển động
    --blur       kích thước GaussianBlur (số lẻ) để giảm nhiễu
    --roi        vùng quan tâm, dạng "x1,y1;x2,y2;x3,y3;..." (polygon)
    --annotate   ghi ảnh/video đã đánh dấu vùng phát hiện
    --max-frames giới hạn số khung hình xử lý (video dài)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - môi trường thiếu thư viện
    print(json.dumps({
        "status": "error",
        "message": "Thiếu opencv-python. Chạy: pip install opencv-python-headless numpy",
    }, ensure_ascii=False))
    sys.exit(1)


# ============================== Tiện ích ==============================

def parse_roi(spec: str | None) -> np.ndarray | None:
    """Chuyển "x1,y1;x2,y2;..." thành mảng điểm (N,1,2) cho fillPoly."""
    if not spec:
        return None
    pts: list[tuple[int, int]] = []
    for token in spec.split(";"):
        token = token.strip()
        if not token:
            continue
        try:
            x, y = token.split(",")
            pts.append((int(x), int(y)))
        except ValueError:
            raise SystemExit(json.dumps({
                "status": "error",
                "message": f"ROI sai định dạng: '{token}' (cần 'x,y')",
            }, ensure_ascii=False))
    if len(pts) < 3:
        raise SystemExit(json.dumps({
            "status": "error",
            "message": "ROI cần ít nhất 3 điểm",
        }, ensure_ascii=False))
    return np.array(pts, dtype=np.int32).reshape((-1, 1, 2))


def apply_roi(gray: np.ndarray, roi: np.ndarray | None) -> np.ndarray:
    """Xoá vùng ngoài ROI (đặt về 0) để bỏ qua bầu trời, cây cối xa..."""
    if roi is None:
        return gray
    mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.fillPoly(mask, [roi], 255)
    return cv2.bitwise_and(gray, gray, mask=mask)


def read_gray(path: str, blur: int, roi: np.ndarray | None) -> np.ndarray | None:
    """Đọc ảnh, chuyển xám, làm mờ, áp ROI. Trả None nếu không đọc được."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    img = cv2.GaussianBlur(img, (blur, blur), 0)
    return apply_roi(img, roi)


def _contours(mask: np.ndarray) -> list[np.ndarray]:
    """Trả danh sách contour, tương thích các phiên bản OpenCV."""
    found = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # OpenCV 3 trả (img, contours, hierarchy); OpenCV 4+ trả (contours, hierarchy)
    return list(found[1] if len(found) == 3 else found[0])


def _motion_regions(diff: np.ndarray, threshold: int, min_area: int) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Tìm các vùng có chuyển động từ ảnh sai khác. Trả (regions, mask)."""
    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)

    regions: list[dict[str, Any]] = []
    for cnt in _contours(mask):
        area = float(cv2.contourArea(cnt))
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        regions.append({
            "area": round(area, 1),
            "bbox": [int(x), int(y), int(w), int(h)],
        })
    return regions, mask


def _severity(ratio: float) -> str:
    """Xếp loại mức độ dựa trên tỉ lệ pixel chuyển động/thay đổi."""
    if ratio >= 0.05:
        return "high"
    if ratio >= 0.01:
        return "medium"
    if ratio > 0:
        return "low"
    return "none"


# ====================== Chế độ 1: video motion ======================

def detect_motion_in_video(
    video_path: str,
    *,
    diff_threshold: int,
    min_area: int,
    blur: int,
    roi: np.ndarray | None,
    max_frames: int | None,
    annotate: str | None,
) -> dict[str, Any]:
    """Phát hiện chuyển động bằng frame differencing trên video."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"status": "error", "message": f"Không mở được video: {video_path}"}

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    writer = None
    if annotate:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(annotate, fourcc, fps if fps > 0 else 10.0, (w, h))

    prev: np.ndarray | None = None
    events: list[dict[str, Any]] = []
    frame_idx = 0
    frame_size = 0
    max_ratio = 0.0

    while True:
        if max_frames is not None and frame_idx >= max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (blur, blur), 0)
        gray = apply_roi(gray, roi)
        if frame_size == 0:
            frame_size = int(gray.size)

        if prev is not None:
            diff = cv2.absdiff(prev, gray)
            regions, mask = _motion_regions(diff, diff_threshold, min_area)
            motion_pixels = int(cv2.countNonZero(mask))
            ratio = motion_pixels / frame_size if frame_size else 0.0
            max_ratio = max(max_ratio, ratio)
            if regions:
                events.append({
                    "frame": frame_idx,
                    "time_sec": round(frame_idx / fps, 3) if fps > 0 else None,
                    "region_count": len(regions),
                    "motion_pixels": motion_pixels,
                    "motion_ratio": round(ratio, 5),
                    "regions": regions,
                })
            if writer is not None:
                annotated = frame.copy()
                for r in regions:
                    x, y, w, h = r["bbox"]
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)
                writer.write(annotated)

        prev = gray
        frame_idx += 1

    cap.release()
    if writer is not None:
        writer.release()

    detected = len(events) > 0
    return {
        "status": "ok",
        "mode": "video_motion",
        "input": video_path,
        "detected": detected,
        "severity": _severity(max_ratio),
        "settings": {
            "diff_threshold": diff_threshold,
            "min_area": min_area,
            "blur": blur,
            "roi": bool(roi is not None),
            "fps": fps,
            "total_frames": total_frames,
            "frames_processed": frame_idx,
        },
        "summary": {
            "frames_with_motion": len(events),
            "max_motion_ratio": round(max_ratio, 5),
        },
        "events": events,
        "annotated": annotate,
        "message": (
            f"Phát hiện chuyển động ở {len(events)}/{frame_idx} khung hình "
            f"(tỉ lệ pixel lớn nhất {max_ratio:.2%})" if detected
            else f"Không phát hiện chuyển động ({frame_idx} khung hình đã xử lý)"
        ),
    }


# ==================== Chế độ 2: change detection ====================

def detect_change(
    reference_path: str,
    current_path: str,
    *,
    diff_threshold: int,
    min_area: int,
    blur: int,
    roi: np.ndarray | None,
    annotate: str | None,
) -> dict[str, Any]:
    """Phát hiện thay đổi giữa ảnh tham chiếu và ảnh hiện tại."""
    ref = read_gray(reference_path, blur, roi)
    cur = read_gray(current_path, blur, roi)
    if ref is None:
        return {"status": "error", "message": f"Không đọc được ảnh tham chiếu: {reference_path}"}
    if cur is None:
        return {"status": "error", "message": f"Không đọc được ảnh: {current_path}"}
    if ref.shape != cur.shape:
        return {
            "status": "error",
            "message": (
                f"Kích thước ảnh khác nhau: reference {ref.shape} vs current {cur.shape}. "
                "Hai ảnh phải cùng độ phân giải."
            ),
        }

    diff = cv2.absdiff(ref, cur)
    regions, mask = _motion_regions(diff, diff_threshold, min_area)
    change_pixels = int(cv2.countNonZero(mask))
    ratio = change_pixels / mask.size if mask.size else 0.0
    detected = ratio > 0.0 and len(regions) > 0

    if annotate:
        img = cv2.imread(current_path)
        if img is not None:
            for r in regions:
                x, y, w, h = r["bbox"]
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.imwrite(annotate, img)

    return {
        "status": "ok",
        "mode": "change_detection",
        "input": current_path,
        "reference": reference_path,
        "detected": detected,
        "severity": _severity(ratio),
        "settings": {"diff_threshold": diff_threshold, "min_area": min_area, "blur": blur, "roi": bool(roi is not None)},
        "summary": {
            "change_ratio": round(ratio, 5),
            "region_count": len(regions),
            "max_region_area": round(max((r["area"] for r in regions), default=0.0), 1),
        },
        "regions": regions,
        "annotated": annotate,
        "message": (
            f"Phát hiện {len(regions)} vùng thay đổi (tỉ lệ {ratio:.2%}) so với ảnh tham chiếu"
            if detected else "Không phát hiện thay đổi đáng kể so với ảnh tham chiếu"
        ),
    }


# ==================== Chế độ 3: single image ====================

def analyze_single_image(image_path: str, blur: int, roi: np.ndarray | None) -> dict[str, Any]:
    """Ảnh đơn: trả thống kê; không kết luận chuyển động (cần video/ảnh tham chiếu)."""
    gray = read_gray(image_path, blur, roi)
    if gray is None:
        return {"status": "error", "message": f"Không đọc được ảnh: {image_path}"}

    edges = cv2.Canny(gray, 50, 150)
    return {
        "status": "ok",
        "mode": "single_image",
        "input": image_path,
        "detected": None,
        "note": "Một ảnh đơn không đủ để phát hiện chuyển động/sạt lở; hãy cung cấp --video hoặc --reference.",
        "metrics": {
            "edge_density": round(float(np.count_nonzero(edges)) / edges.size, 5),
            "mean_intensity": round(float(np.mean(gray)), 2),
            "std_intensity": round(float(np.std(gray)), 2),
        },
    }


# ============================== Main ==============================

def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Phát hiện chuyển động / sạt lở thật cho giám sát đường sắt (OpenCV)",
    )
    parser.add_argument("--image", help="Đường dẫn ảnh cần phân tích")
    parser.add_argument("--video", help="Đường dẫn video cần phân tích chuyển động")
    parser.add_argument("--reference", help="Ảnh tham chiếu (baseline) để phát hiện thay đổi")
    parser.add_argument("--threshold", type=int, default=25,
                        help="Ngưỡng sai khác xám 0-255 (mặc định 25; càng nhỏ càng nhạy)")
    parser.add_argument("--min-area", type=int, default=500,
                        help="Diện tích contour tối thiểu (px) để tính là chuyển động (mặc định 500)")
    parser.add_argument("--blur", type=int, default=21,
                        help="Kích thước GaussianBlur, số lẻ (mặc định 21)")
    parser.add_argument("--roi", help='Vùng quan tâm dạng "x1,y1;x2,y2;x3,y3;..."')
    parser.add_argument("--max-frames", type=int, default=None, help="Giới hạn số khung hình (video)")
    parser.add_argument("--annotate", help="Ghi ảnh/video đã đánh dấu vùng phát hiện ra đường dẫn này")
    parser.add_argument("--save-result", action="store_true", help="Lưu kết quả JSON cạnh file đầu vào")
    args = parser.parse_args(argv)

    if not args.image and not args.video:
        parser.error("cần ít nhất một trong --image hoặc --video")

    if args.reference and not args.image:
        parser.error("--reference chỉ dùng kèm với --image")

    roi = parse_roi(args.roi)

    if args.video:
        result = detect_motion_in_video(
            args.video,
            diff_threshold=args.threshold,
            min_area=args.min_area,
            blur=args.blur,
            roi=roi,
            max_frames=args.max_frames,
            annotate=args.annotate,
        )
        base_path = Path(args.video)
    elif args.reference:
        result = detect_change(
            args.reference,
            args.image,
            diff_threshold=args.threshold,
            min_area=args.min_area,
            blur=args.blur,
            roi=roi,
            annotate=args.annotate,
        )
        base_path = Path(args.image)
    else:
        result = analyze_single_image(args.image, blur=args.blur, roi=roi)
        base_path = Path(args.image)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.save_result:
        out_path = base_path.with_suffix(".result.json")
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã lưu kết quả: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
