#!/usr/bin/env python3
"""
Nén PDF để gửi qua Telegram (bot giới hạn tải file ≤ 20 MB).

Cách hoạt động:
    1. Nếu file đã nhỏ hơn ngưỡng → giữ nguyên.
    2. Thử nén lossless (garbage collection + deflate, giữ nguyên text layer).
    3. Nếu vẫn lớn → rasterize từng trang thành ảnh JPEG và giảm dần
       dpi/chất lượng cho đến khi dưới ngưỡng.

Chạy:
    python scripts/compress_pdf.py big.pdf                  # -> big_compressed.pdf
    python scripts/compress_pdf.py big.pdf -o small.pdf --target-mb 19

Cần: pip install pymupdf
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def _rasterize(src, out: Path, dpi: int, quality: int) -> None:
    import pymupdf

    new = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi)
        data = pix.tobytes("jpeg", jpg_quality=quality)
        npg = new.new_page(width=page.rect.width, height=page.rect.height)
        npg.insert_image(page.rect, stream=data)
    new.save(str(out), deflate=True)
    new.close()


def compress(
    input_path: Path,
    output_path: Path,
    dpi: int = 150,
    quality: int = 70,
    target_mb: int = 19,
    force_rasterize: bool = False,
) -> str:
    import pymupdf

    target_bytes = target_mb * 1024 * 1024
    orig_mb = _size_mb(input_path)

    # Đã đủ nhỏ → copy nguyên
    if orig_mb <= target_mb:
        output_path.write_bytes(input_path.read_bytes())
        return f"✅ File đã đủ nhỏ ({orig_mb:.2f} MB ≤ {target_mb} MB) — giữ nguyên."

    src = pymupdf.open(str(input_path))
    pages = src.page_count

    # Bước 1: lossless (giữ text layer)
    if not force_rasterize:
        src.save(str(output_path), garbage=4, deflate=True)
        if _size_mb(output_path) <= target_mb:
            src.close()
            return (
                f"✅ Nén lossless: {orig_mb:.2f} MB → {_size_mb(output_path):.2f} MB "
                f"({pages} trang, giữ nguyên văn bản)."
            )

    # Bước 2: rasterize + JPEG, giảm dần
    for d in (dpi, 120, 96, 72):
        for q in (quality, 60, 45):
            _rasterize(src, output_path, d, q)
            if _size_mb(output_path) <= target_mb:
                src.close()
                return (
                    f"✅ Nén rasterize (dpi={d}, quality={q}): "
                    f"{orig_mb:.2f} MB → {_size_mb(output_path):.2f} MB ({pages} trang).\n"
                    f"⚠️ Lưu ý: bản nén là ảnh quét lại, mất text layer (không tìm kiếm được chữ)."
                )

    src.close()
    final = _size_mb(output_path)
    return (
        f"⚠️ Không nén được dưới {target_mb} MB — còn {final:.2f} MB. "
        "Thử giảm số trang hoặc --target-mb cao hơn."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Nén PDF cho dưới giới hạn Telegram (20 MB)")
    parser.add_argument("input", help="Đường dẫn PDF cần nén")
    parser.add_argument("-o", "--output", default=None, help="Đường dẫn PDF đầu ra")
    parser.add_argument("--dpi", type=int, default=150, help="DPI khởi đầu khi rasterize (mặc định 150)")
    parser.add_argument("--quality", type=int, default=70, help="Chất lượng JPEG 1-95 (mặc định 70)")
    parser.add_argument("--target-mb", type=int, default=19, help="Ngưỡng kích thước tối đa MB (mặc định 19)")
    parser.add_argument("--force-rasterize", action="store_true", help="Bỏ qua bước lossless, rasterize luôn")
    args = parser.parse_args()

    inp = Path(args.input).resolve()
    if not inp.is_file():
        raise SystemExit(f"Không tìm thấy file: {inp}")
    out = Path(args.output) if args.output else inp.with_name(inp.stem + "_compressed.pdf")

    print(compress(inp, out, dpi=args.dpi, quality=args.quality,
                   target_mb=args.target_mb, force_rasterize=args.force_rasterize))
    if out.exists():
        print(f"Đầu ra: {out}")


if __name__ == "__main__":
    main()
