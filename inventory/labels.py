"""T50-oriented QR label PNGs (203 dpi, black on white)."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

DPI = 203
LABEL_SIZE_SESSION_KEY = "qr_label_size"
DEFAULT_SIZE_KEY = "40x30"

_FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def mm_to_px(mm: float) -> int:
    return max(1, round(mm / 25.4 * DPI))


@dataclass(frozen=True)
class LabelSize:
    key: str
    name: str
    hint: str
    layout: str
    width_mm: float
    height_mm: float

    @property
    def width_px(self) -> int:
        if self.layout == "cable":
            return mm_to_px(45) + mm_to_px(35)
        return mm_to_px(self.width_mm)

    @property
    def height_px(self) -> int:
        return mm_to_px(self.height_mm)

    @property
    def sil_w(self) -> float:
        return 80 if self.layout == "cable" else self.width_mm

    @property
    def sil_h(self) -> float:
        return 30 if self.layout == "cable" else self.height_mm


LABEL_SIZES: dict[str, LabelSize] = {
    "50x80": LabelSize(
        "50x80",
        "50 × 80 mm",
        "QR, name, number, and location",
        "large",
        50,
        80,
    ),
    "40x30": LabelSize(
        "40x30",
        "40 × 30 mm",
        "QR, name, and number",
        "medium",
        40,
        30,
    ),
    "40x20": LabelSize(
        "40x20",
        "40 × 20 mm",
        "Compact: QR and number",
        "compact",
        40,
        20,
    ),
    "30x20": LabelSize(
        "30x20",
        "30 × 20 mm",
        "Small parts: QR and number",
        "compact",
        30,
        20,
    ),
    "cable-flag": LabelSize(
        "cable-flag",
        "Cable flag",
        "45 × 30 mm fold (two 45 × 15 mm faces) + 35 × 7 mm wrap",
        "cable",
        80,
        30,
    ),
}

LABEL_SIZE_LIST = tuple(LABEL_SIZES.values())


def get_label_size(key: str | None) -> LabelSize:
    if key and key in LABEL_SIZES:
        return LABEL_SIZES[key]
    return LABEL_SIZES[DEFAULT_SIZE_KEY]


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _FONT_BOLD if bold else _FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _qr(url: str, box_px: int) -> Image.Image:
    qr = segno.make(url, error="m")
    buf = BytesIO()
    qr.save(buf, kind="png", scale=8, border=2, dark="#000000", light="#ffffff")
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    return img.resize((box_px, box_px), Image.Resampling.NEAREST)


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    text = text or ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ell = "…"
    if not text:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        trial = text[:mid].rstrip() + ell
        if draw.textlength(trial, font=font) <= max_width:
            lo = mid + 1
        else:
            hi = mid
    cut = max(1, lo - 1)
    return text[:cut].rstrip() + ell


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines:
        lines[-1] = _ellipsize(draw, lines[-1], font, max_width)
    return lines[:max_lines]


def _paste_qr(canvas: Image.Image, url: str, box: int, xy: tuple[int, int]) -> None:
    canvas.paste(_qr(url, box), xy)


def _draw_text_block(draw, lines, font, x, y, line_gap=4, fill=0):
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y = bbox[3] + line_gap
    return y


def render_label_png(url: str, title: str, subtitle: str, extra: str, size: LabelSize) -> bytes:
    if size.layout == "cable":
        img = _render_cable(url, title, subtitle)
    elif size.layout == "large":
        img = _render_large(url, title, subtitle, extra, size)
    elif size.layout == "medium":
        img = _render_medium(url, title, subtitle, size)
    else:
        img = _render_compact(url, title, subtitle, size)
    buf = BytesIO()
    img.convert("1", dither=Image.Dither.NONE).save(buf, format="PNG")
    return buf.getvalue()


def _blank(size: LabelSize) -> Image.Image:
    return Image.new("RGB", (size.width_px, size.height_px), "white")


def _render_large(url, title, subtitle, extra, size: LabelSize) -> Image.Image:
    img = _blank(size)
    draw = ImageDraw.Draw(img)
    pad = mm_to_px(3)
    qr_box = min(size.width_px - 2 * pad, mm_to_px(36))
    _paste_qr(img, url, qr_box, ((size.width_px - qr_box) // 2, pad))
    y = pad + qr_box + mm_to_px(2)
    title_font = _font(22, bold=True)
    sub_font = _font(18, bold=True)
    extra_font = _font(16)
    max_w = size.width_px - 2 * pad
    y = _draw_text_block(draw, _wrap(draw, title, title_font, max_w, 3), title_font, pad, y)
    if subtitle:
        y = _draw_text_block(draw, [subtitle], sub_font, pad, y)
    if extra:
        _draw_text_block(draw, _wrap(draw, extra, extra_font, max_w, 2), extra_font, pad, y)
    return img


def _render_medium(url, title, subtitle, size: LabelSize) -> Image.Image:
    img = _blank(size)
    draw = ImageDraw.Draw(img)
    pad = mm_to_px(1.4)
    gap = mm_to_px(1.2)
    text_col = max(mm_to_px(16), int(size.width_px * 0.44))
    qr_box = min(
        size.height_px - 2 * pad,
        size.width_px - 2 * pad - gap - text_col,
        mm_to_px(18),
    )
    _paste_qr(img, url, qr_box, (pad, pad))
    x = pad + qr_box + gap
    max_w = size.width_px - x - pad
    title_font = _font(12, bold=True)
    sub_font = _font(11, bold=True)
    y = pad
    y = _draw_text_block(
        draw, _wrap(draw, title, title_font, max_w, 3), title_font, x, y, line_gap=1
    )
    if subtitle:
        draw.text((x, y + 1), _ellipsize(draw, subtitle, sub_font, max_w), font=sub_font, fill=0)
    return img


def _render_compact(url, title, subtitle, size: LabelSize) -> Image.Image:
    img = _blank(size)
    draw = ImageDraw.Draw(img)
    pad = mm_to_px(1.2)
    qr_box = size.height_px - 2 * pad
    _paste_qr(img, url, qr_box, (pad, pad))
    x = pad + qr_box + mm_to_px(1)
    max_w = size.width_px - x - pad
    number = subtitle or title
    num_font = _font(13, bold=True)
    name_font = _font(11)
    y = pad
    draw.text((x, y), _ellipsize(draw, number, num_font, max_w), font=num_font, fill=0)
    bbox = draw.textbbox((x, y), number, font=num_font)
    y = bbox[3] + 2
    if title and title != number:
        leftover = size.height_px - pad - y
        if leftover > 12:
            for line in _wrap(draw, title, name_font, max_w, 2):
                draw.text((x, y), line, font=name_font, fill=0)
                y = draw.textbbox((x, y), line, font=name_font)[3] + 1
    return img


def _render_cable(url: str, title: str, number: str) -> Image.Image:
    """45×30 mm flag (two 45×15 faces) plus 35×7 mm wrap tab on the right."""
    body_w, body_h = mm_to_px(45), mm_to_px(30)
    face_h = mm_to_px(15)
    tab_w, tab_h = mm_to_px(35), mm_to_px(7)
    canvas = Image.new("RGB", (body_w + tab_w, body_h), "white")
    face = _cable_face(url, title, number, body_w, face_h)
    canvas.paste(face, (0, 0))
    canvas.paste(face.rotate(180), (0, face_h))
    draw = ImageDraw.Draw(canvas)
    y_fold = face_h
    for x in range(0, body_w, 6):
        draw.point((x, y_fold), fill=0)
        draw.point((x + 1, y_fold), fill=0)
    tab_y = (body_h - tab_h) // 2
    draw.rectangle(
        [body_w, tab_y, body_w + tab_w - 1, tab_y + tab_h - 1],
        outline=0,
        width=1,
    )
    return canvas


def _cable_face(url: str, title: str, number: str, width: int, height: int) -> Image.Image:
    face = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(face)
    pad = mm_to_px(0.9)
    qr_box = min(height - 2 * pad, mm_to_px(11))
    _paste_qr(face, url, qr_box, (pad, (height - qr_box) // 2))
    x = pad + qr_box + mm_to_px(1)
    max_w = width - x - pad
    num_font = _font(10, bold=True)
    name_font = _font(9)
    y = pad
    label = number or title
    draw.text((x, y), _ellipsize(draw, label, num_font, max_w), font=num_font, fill=0)
    bbox = draw.textbbox((x, y), label, font=num_font)
    y = bbox[3] + 1
    if title and title != label:
        leftover = height - pad - y
        max_lines = 2 if leftover > 18 else 1
        if leftover > 10:
            for line in _wrap(draw, title, name_font, max_w, max_lines):
                draw.text((x, y), line, font=name_font, fill=0)
                y = draw.textbbox((x, y), line, font=name_font)[3]
    return face


def png_filename(stem: str, size: LabelSize) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    return f"{safe}-{size.key}.png"
