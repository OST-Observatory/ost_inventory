"""T50-oriented QR label PNGs (203 dpi, black on white)."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

# T50 is 203 dpi = 8 dots/mm. The print head covers 48 mm of a 50 mm tape.
DPI = 203
DOTS_PER_MM = 8
RENDER_SCALE = 2
LABEL_SIZE_SESSION_KEY = "qr_label_size"
DEFAULT_SIZE_KEY = "40x30"

_FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# Inner inset, ~3× the previous values, so die-cut / head margins do not clip.
MARGIN_LARGE_MM = 9.0
MARGIN_MEDIUM_MM = 4.2
MARGIN_COMPACT_MM = 3.6
MARGIN_CABLE_MM = 2.7


def mm_to_px(mm: float) -> int:
    return max(1, round(mm * DOTS_PER_MM))


def _px(mm: float, scale: int) -> int:
    return mm_to_px(mm) * scale


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
    def sil_box_style(self) -> str:
        """Picker size at the shared mm scale (must match app.css; no inline styles)."""
        w, h = sil_rem(self.width_mm, self.height_mm)
        return f"width:{w:.3f}rem;height:{h:.3f}rem;"


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

# Picker silhouettes share one mm scale so 50×80 is larger than 40×30, not a thin bar.
SIL_FIT_W_REM = 5.5
SIL_FIT_H_REM = 4.0
CABLE_FLAG_MM = (45.0, 30.0)
CABLE_TAB_MM = (35.0, 7.0)


def silhouette_scale() -> float:
    max_w = max(
        CABLE_FLAG_MM[0] + CABLE_TAB_MM[0] if s.layout == "cable" else s.width_mm
        for s in LABEL_SIZES.values()
    )
    max_h = max(
        CABLE_FLAG_MM[1] if s.layout == "cable" else s.height_mm
        for s in LABEL_SIZES.values()
    )
    return min(SIL_FIT_W_REM / max_w, SIL_FIT_H_REM / max_h)


def sil_rem(width_mm: float, height_mm: float) -> tuple[float, float]:
    scale = silhouette_scale()
    return width_mm * scale, height_mm * scale


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
    """Integer-module QR, centered in box_px so thermal dots stay aligned."""
    qr = segno.make(url, error="m")
    modules = qr.symbol_size(scale=1, border=2)[0]
    scale = max(1, box_px // modules)
    buf = BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2, dark="#000000", light="#ffffff")
    buf.seek(0)
    tile = Image.open(buf).convert("RGB")
    if tile.size[0] > box_px:
        tile = tile.resize((box_px, box_px), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (box_px, box_px), "white")
    x = (box_px - tile.size[0]) // 2
    y = (box_px - tile.size[1]) // 2
    canvas.paste(tile, (x, y))
    return canvas


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


def _draw_text_block(draw, lines, font, x, y, line_gap=4, fill=0, max_y=None):
    for line in lines:
        bbox = draw.textbbox((x, y), line, font=font)
        if max_y is not None and bbox[3] > max_y:
            break
        draw.text((x, y), line, font=font, fill=fill)
        y = bbox[3] + line_gap
    return y


def _finalize(img: Image.Image, out_size: tuple[int, int]) -> Image.Image:
    """Downsample 2× art and snap to pure B/W for the T50 (no 1-bit PNG)."""
    if img.size != out_size:
        img = img.resize(out_size, Image.Resampling.BOX)
    return img.convert("L").point(lambda p: 0 if p < 200 else 255, "L").convert("RGB")


def render_label_png(url: str, title: str, subtitle: str, extra: str, size: LabelSize) -> bytes:
    scale = RENDER_SCALE
    if size.layout == "cable":
        img = _render_cable(url, title, subtitle, scale)
    elif size.layout == "large":
        img = _render_large(url, title, subtitle, extra, size, scale)
    elif size.layout == "medium":
        img = _render_medium(url, title, subtitle, size, scale)
    else:
        img = _render_compact(url, title, subtitle, size, scale)
    img = _finalize(img, (size.width_px, size.height_px))
    buf = BytesIO()
    img.save(buf, format="PNG", dpi=(DPI, DPI), optimize=True)
    return buf.getvalue()


def _blank(width_px: int, height_px: int, scale: int) -> Image.Image:
    return Image.new("RGB", (width_px * scale, height_px * scale), "white")


def _render_large(url, title, subtitle, extra, size: LabelSize, scale: int) -> Image.Image:
    img = _blank(size.width_px, size.height_px, scale)
    draw = ImageDraw.Draw(img)
    pad = _px(MARGIN_LARGE_MM, scale)
    max_y = img.size[1] - pad
    qr_box = min(img.size[0] - 2 * pad, _px(36, scale))
    _paste_qr(img, url, qr_box, ((img.size[0] - qr_box) // 2, pad))
    y = pad + qr_box + _px(2, scale)
    title_font = _font(22 * scale, bold=True)
    sub_font = _font(18 * scale, bold=True)
    extra_font = _font(16 * scale)
    max_w = img.size[0] - 2 * pad
    gap = 4 * scale
    y = _draw_text_block(
        draw, _wrap(draw, title, title_font, max_w, 3), title_font, pad, y, gap, max_y=max_y
    )
    if subtitle:
        y = _draw_text_block(draw, [subtitle], sub_font, pad, y, gap, max_y=max_y)
    if extra:
        _draw_text_block(
            draw, _wrap(draw, extra, extra_font, max_w, 2), extra_font, pad, y, gap, max_y=max_y
        )
    return img


def _render_medium(url, title, subtitle, size: LabelSize, scale: int) -> Image.Image:
    img = _blank(size.width_px, size.height_px, scale)
    draw = ImageDraw.Draw(img)
    pad = _px(MARGIN_MEDIUM_MM, scale)
    gap = _px(1.2, scale)
    inner_w = img.size[0] - 2 * pad
    inner_h = img.size[1] - 2 * pad
    qr_box = min(inner_h, _px(18, scale), inner_w * 55 // 100)
    _paste_qr(img, url, qr_box, (pad, pad))
    x = pad + qr_box + gap
    max_w = img.size[0] - x - pad
    max_y = img.size[1] - pad
    title_font = _font(12 * scale, bold=True)
    sub_font = _font(11 * scale, bold=True)
    y = pad
    y = _draw_text_block(
        draw,
        _wrap(draw, title, title_font, max_w, 3),
        title_font,
        x,
        y,
        line_gap=scale,
        max_y=max_y,
    )
    if subtitle:
        line = _ellipsize(draw, subtitle, sub_font, max_w)
        bbox = draw.textbbox((x, y + scale), line, font=sub_font)
        if bbox[3] <= max_y:
            draw.text((x, y + scale), line, font=sub_font, fill=0)
    return img


def _render_compact(url, title, subtitle, size: LabelSize, scale: int) -> Image.Image:
    img = _blank(size.width_px, size.height_px, scale)
    draw = ImageDraw.Draw(img)
    pad = _px(MARGIN_COMPACT_MM, scale)
    qr_box = img.size[1] - 2 * pad
    _paste_qr(img, url, qr_box, (pad, pad))
    x = pad + qr_box + _px(1, scale)
    max_w = img.size[0] - x - pad
    max_y = img.size[1] - pad
    number = subtitle or title
    num_font = _font(13 * scale, bold=True)
    name_font = _font(11 * scale)
    y = pad
    num = _ellipsize(draw, number, num_font, max_w)
    draw.text((x, y), num, font=num_font, fill=0)
    bbox = draw.textbbox((x, y), num, font=num_font)
    y = bbox[3] + 2 * scale
    if title and title != number:
        leftover = max_y - y
        if leftover > 12 * scale:
            for line in _wrap(draw, title, name_font, max_w, 2):
                bbox = draw.textbbox((x, y), line, font=name_font)
                if bbox[3] > max_y:
                    break
                draw.text((x, y), line, font=name_font, fill=0)
                y = bbox[3] + scale
    return img


def _render_cable(url: str, title: str, number: str, scale: int) -> Image.Image:
    """45×30 mm flag (two 45×15 faces) plus 35×7 mm wrap tab on the right."""
    body_w, body_h = _px(45, scale), _px(30, scale)
    face_h = _px(15, scale)
    tab_w, tab_h = _px(35, scale), _px(7, scale)
    canvas = Image.new("RGB", (body_w + tab_w, body_h), "white")
    face = _cable_face(url, title, number, body_w, face_h, scale)
    canvas.paste(face, (0, 0))
    canvas.paste(face.rotate(180), (0, face_h))
    draw = ImageDraw.Draw(canvas)
    y_fold = face_h
    for x in range(0, body_w, 6 * scale):
        draw.point((x, y_fold), fill=0)
        draw.point((x + scale, y_fold), fill=0)
    # Keep the 7 mm wrap outline close to its die-cut; only a 1 mm inset.
    tab_inset = _px(1.0, scale)
    tab_y = (body_h - tab_h) // 2
    draw.rectangle(
        [
            body_w + tab_inset,
            tab_y + tab_inset,
            body_w + tab_w - 1 - tab_inset,
            tab_y + tab_h - 1 - tab_inset,
        ],
        outline=0,
        width=max(1, scale),
    )
    return canvas


def _cable_face(url: str, title: str, number: str, width: int, height: int, scale: int) -> Image.Image:
    face = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(face)
    pad = _px(MARGIN_CABLE_MM, scale)
    qr_box = min(height - 2 * pad, _px(11, scale))
    _paste_qr(face, url, qr_box, (pad, (height - qr_box) // 2))
    x = pad + qr_box + _px(1, scale)
    max_w = width - x - pad
    max_y = height - pad
    num_font = _font(10 * scale, bold=True)
    name_font = _font(9 * scale)
    y = pad
    label = number or title
    line = _ellipsize(draw, label, num_font, max_w)
    draw.text((x, y), line, font=num_font, fill=0)
    bbox = draw.textbbox((x, y), line, font=num_font)
    y = bbox[3] + scale
    if title and title != label:
        leftover = max_y - y
        max_lines = 2 if leftover > 18 * scale else 1
        if leftover > 10 * scale:
            for text_line in _wrap(draw, title, name_font, max_w, max_lines):
                bbox = draw.textbbox((x, y), text_line, font=name_font)
                if bbox[3] > max_y:
                    break
                draw.text((x, y), text_line, font=name_font, fill=0)
                y = bbox[3]
    return face


def png_filename(stem: str, size: LabelSize) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    return f"{safe}-{size.key}.png"
