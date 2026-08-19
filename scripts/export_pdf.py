#!/usr/bin/env python3
"""
Xuất SANG_KIEN.md ra PDF (A4) bằng fpdf2 + font DejaVu (hỗ trợ tiếng Việt).

Chạy:
    python scripts/export_pdf.py [input.md] [output.pdf]

Mặc định đọc SANG_KIEN.md và ghi SANG_KIEN.pdf tại thư mục gốc repo.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

BASE = Path(__file__).parent.parent.resolve()
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

DEFAULT_IN = BASE / "SANG_KIEN.md"
DEFAULT_OUT = BASE / "SANG_KIEN.pdf"

# ============================== Làm sạch ký tự ==============================

# Emoji màu không có trong DejaVu → thay bằng ký hiệu đơn sắc hoặc bỏ.
EMOJI_MAP = {
    "✅": "✓",
    "🔶": "◆",
    "🚆": "",
    "📊": "",
    "📚": "",
    "📌": "",
    "📄": "",
    "🔍": "",
    "🔧": "",
    "📡": "",
    "🤖": "",
    "⏳": "",
    "⚠": "⚠",  # DejaVu có glyph cảnh báo đơn sắc
}


def clean_text(text: str) -> str:
    for k, v in EMOJI_MAP.items():
        text = text.replace(k, v)
    # Bỏ variation selector và emoji màu còn sót (U+1F000–U+1FFFF, U+FE00–U+FE0F)
    text = re.sub(r"[\U0001F000-\U0001FFFF\uFE00-\uFE0F]", "", text)
    return text


# ============================== Inline markdown ==============================

INLINE_RE = re.compile(
    r"(\*\*.+?\*\*|`[^`]+`|\*[^*]+\*|\[[^\]]+\]\([^)]*\))"
)


def strip_inline(text: str) -> str:
    """Bỏ cú pháp inline (dùng cho ô bảng): **bold** -> bold, `code` -> code..."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return text


class ReportPdf(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(auto=True, margin=20)
        self._register_fonts()
        self._page_count = 0

    def _register_fonts(self) -> None:
        self.add_font("Sans", "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("Sans", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font("Mono", "", str(FONT_DIR / "DejaVuSansMono.ttf"))
        self.add_font("Mono", "B", str(FONT_DIR / "DejaVuSansMono-Bold.ttf"))

    def footer(self) -> None:
        self._page_count += 1
        self.set_y(-14)
        self.set_font("Sans", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Railway Hermes Agent — Bản sáng kiến · Trang {self._page_count}", align="C")

    # --- helpers ---------------------------------------------------------
    def write_inline(self, text: str, size: float, color=(40, 40, 40)) -> None:
        """Viết một đoạn có inline **bold** / `code` / *italic* / [link]."""
        self.set_text_color(*color)
        pos = 0
        for m in INLINE_RE.finditer(text):
            if m.start() > pos:
                self._plain(text[pos:m.start()], size)
            token = m.group(0)
            if token.startswith("**"):
                self._seg(token[2:-2], size, style="B")
            elif token.startswith("`"):
                self._seg(token[1:-1], size - 0.5, style="M")
            elif token.startswith("*"):
                self._seg(token[1:-1], size, style="")
            else:  # [text](url)
                label = re.match(r"\[([^\]]+)\]", token).group(1)
                self._seg(label, size, style="", link=re.search(r"\((.*)\)", token).group(1))
        if pos < len(text):
            self._plain(text[pos:], size)

    def _plain(self, text: str, size: float) -> None:
        self.set_font("Sans", "", size)
        self.write(size * 0.52, text)

    def _seg(self, text: str, size: float, style: str, link: str | None = None) -> None:
        family = "Mono" if style == "M" else "Sans"
        self.set_font(family, "B" if style == "B" else "", size)
        if link:
            self.set_text_color(30, 90, 200)
        self.write(size * 0.52, text)
        self.set_text_color(40, 40, 40)

    def heading(self, text: str, size: float, color: tuple, space_before: float = 4) -> None:
        self.ln(space_before)
        self.set_font("Sans", "B", size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.42, text)
        self.ln(1.2)

    def paragraph(self, text: str) -> None:
        self.set_font("Sans", "", 10)
        self.write_inline(text, 10)
        self.ln(3.5)

    def bullet(self, text: str) -> None:
        self.set_font("Sans", "", 10)
        x = self.get_x()
        self.cell(5, 5, "•")
        self.set_x(x + 5)
        self.write_inline(text, 10)
        self.ln(3.2)

    def code_block(self, lines: list[str]) -> None:
        self.ln(1)
        # Dùng font Sans (không phải Mono) vì sơ đồ chứa tiếng Việt có dấu;
        # DejaVu Sans Mono thiếu một số glyph tiếng Việt (ả, ế...).
        self.set_font("Sans", "", 8)
        self.set_fill_color(245, 247, 250)
        self.set_text_color(40, 44, 52)
        x, y = self.get_x(), self.get_y()
        for line in lines:
            self.set_x(x)
            self.cell(0, 4.1, line or " ", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(40, 40, 40)
        self.ln(2)

    def render_table(self, rows: list[list[str]], header: bool = True) -> None:
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        # Chuẩn hoá số cột
        rows = [r + [""] * (ncols - len(r)) for r in rows]
        usable = self.epw  # effective page width
        col_w = [usable / ncols] * ncols
        self.ln(1)
        self.set_font("Sans", "B", 8.5)
        with super().table(
            col_widths=col_w,
            text_align="LEFT",
            borders_layout="HORIZONTAL_LINES",
            line_height=4.4,
            padding=1.2,
        ) as tb:
            if header:
                hr = tb.row()
                for c in rows[0]:
                    hr.cell(strip_inline(c))
                rows = rows[1:]
            self.set_font("Sans", "", 8.5)
            for r in rows:
                tr = tb.row()
                for c in r:
                    tr.cell(strip_inline(c))
        self.ln(2)

    def rule(self) -> None:
        self.ln(2)
        y = self.get_y()
        self.set_draw_color(180, 185, 195)
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.set_draw_color(0, 0, 0)
        self.ln(2)


# ============================== Parse markdown ==============================

def parse_blocks(text: str) -> list[tuple[str, object]]:
    lines = text.splitlines()
    blocks: list[tuple[str, object]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            code: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # bỏ dòng đóng ```
            blocks.append(("code", code))
            continue
        if stripped.startswith("#### "):
            blocks.append(("h4", stripped[5:].strip()))
        elif stripped.startswith("### "):
            blocks.append(("h3", stripped[4:].strip()))
        elif stripped.startswith("## "):
            blocks.append(("h2", stripped[3:].strip()))
        elif stripped.startswith("# "):
            blocks.append(("h1", stripped[2:].strip()))
        elif stripped == "---":
            blocks.append(("rule", None))
        elif stripped.startswith("|"):
            table: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                # bỏ dòng phân cách header (|---|---|)
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    table.append(cells)
                i += 1
            blocks.append(("table", table))
            continue
        elif stripped.startswith("> "):
            quote = [stripped[2:]]
            i += 1
            while i < n and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("quote", " ".join(quote)))
            continue
        elif re.match(r"^\d+\.\s", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s", "", lines[i].strip()))
                i += 1
            blocks.append(("ol", items))
            continue
        elif stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("ul", items))
            continue
        else:
            # gộp dòng liên tiếp thành đoạn
            para = [stripped]
            i += 1
            while i < n and lines[i].strip() and not lines[i].strip().startswith(("#", "|", "```", ">", "- ", "---")):
                para.append(lines[i].strip())
                i += 1
            blocks.append(("p", " ".join(para)))
            continue
        i += 1
    return blocks


# ============================== Render ==============================

def render(text: str, out: Path) -> None:
    pdf = ReportPdf()
    pdf.add_page()
    blocks = parse_blocks(text)

    for kind, payload in blocks:
        if kind == "h1":
            pdf.heading(str(payload), 16, (15, 40, 90), space_before=0)
        elif kind == "h2":
            pdf.heading(str(payload), 13, (15, 40, 90), space_before=5)
        elif kind == "h3":
            pdf.heading(str(payload), 11.5, (40, 50, 70), space_before=3)
        elif kind == "h4":
            pdf.heading(str(payload), 10.5, (60, 70, 90), space_before=2)
        elif kind == "p":
            pdf.paragraph(str(payload))
        elif kind == "quote":
            pdf.set_font("Sans", "", 9.5)
            pdf.set_text_color(90, 100, 115)
            pdf.write_inline(str(payload), 9.5, color=(90, 100, 115))
            pdf.set_text_color(40, 40, 40)
            pdf.ln(3.5)
        elif kind == "ul":
            for it in payload:
                pdf.bullet(it)
        elif kind == "ol":
            for idx, it in enumerate(payload, 1):
                pdf.set_font("Sans", "", 10)
                x = pdf.get_x()
                pdf.cell(7, 5, f"{idx}.")
                pdf.set_x(x + 7)
                pdf.write_inline(it, 10)
                pdf.ln(3.2)
        elif kind == "code":
            pdf.code_block(list(payload))
        elif kind == "table":
            pdf.render_table(list(payload))
        elif kind == "rule":
            pdf.rule()

    pdf.output(str(out))
    print(f"✅ Đã xuất: {out} ({len(blocks)} khối)")


def main() -> None:
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    text = clean_text(inp.read_text(encoding="utf-8"))
    render(text, out)


if __name__ == "__main__":
    main()
