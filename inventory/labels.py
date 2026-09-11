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
TEXT_SCALE = 4
_BW_CUTOFF = 155
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
        "Large QR, inventory number and name beside",
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


_PROBE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _FONT_BOLD if bold else _FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), max(1, size))
    except OSError:
        return ImageFont.load_default()


def _fit_font(text: str, max_width: int, max_px: int, *, bold: bool = False, min_px: int = 8):
    lo, hi = min_px, max(min_px, max_px)
    best = min_px
    sample = text or " "
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _font(mid, bold=bold)
        if _PROBE.textlength(sample, font=font) <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return _font(best, bold=bold)


def _qr(url: str, box_px: int, *, border: int | None = None) -> Image.Image:
    """Integer-module QR, centered in box_px so thermal dots stay aligned."""
    qr = segno.make(url, error="m")
    if border is None:
        # Small boxes: the label pad is the quiet zone; extra modules steal scan size.
        border = 2 if box_px >= mm_to_px(24) else 0
    modules = qr.symbol_size(scale=1, border=border)[0]
    scale = max(1, box_px // modules)
    buf = BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border, dark="#000000", light="#ffffff")
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


def _sharp_text_image(width: int, height: int, painter) -> Image.Image:
    """Paint text at 4×, LANCZOS down, then snap to B/W so thermal type stays dense."""
    s = TEXT_SCALE
    layer = Image.new("RGB", (max(1, width) * s, max(1, height) * s), "white")
    painter(ImageDraw.Draw(layer), s)
    out = (max(1, width), max(1, height))
    if layer.size != out:
        layer = layer.resize(out, Image.Resampling.LANCZOS)
    return layer.convert("L").point(lambda p: 0 if p < _BW_CUTOFF else 255, "L").convert("RGB")


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
    img.save(buf, format="PNG", dpi=(DPI, DPI), optimize=True)
    return buf.getvalue()


def _render_large(url, title, subtitle, extra, size: LabelSize) -> Image.Image:
    img = Image.new("RGB", (size.width_px, size.height_px), "white")
    pad = mm_to_px(MARGIN_LARGE_MM)
    qr_box = min(size.width_px - 2 * pad, mm_to_px(36))
    _paste_qr(img, url, qr_box, ((size.width_px - qr_box) // 2, pad))
    text_y = pad + qr_box + mm_to_px(2)
    text_h = size.height_px - pad - text_y
    text_w = size.width_px - 2 * pad
    if text_w > 4 and text_h > 4:
        img.paste(
            _sharp_text_image(
                text_w,
                text_h,
                lambda draw, s: _paint_stacked_text(
                    draw,
                    s,
                    text_w,
                    text_h,
                    title,
                    subtitle,
                    extra,
                    title_px=26,
                    sub_px=20,
                    extra_px=18,
                    title_lines=3,
                    extra_lines=2,
                ),
            ),
            (pad, text_y),
        )
    return img


def _paint_stacked_text(
    draw,
    s,
    width,
    height,
    title,
    subtitle,
    extra,
    *,
    title_px,
    sub_px,
    extra_px,
    title_lines,
    extra_lines,
):
    pad = s
    x = pad
    y = pad
    max_w = width * s - 2 * pad
    max_y = height * s - pad
    gap = 4 * s
    title_font = _font(title_px * s, bold=True)
    y = _draw_text_block(
        draw, _wrap(draw, title, title_font, max_w, title_lines), title_font, x, y, gap, max_y=max_y
    )
    if subtitle:
        sub_font = _font(sub_px * s, bold=True)
        y = _draw_text_block(draw, [subtitle], sub_font, x, y, gap, max_y=max_y)
    if extra:
        extra_font = _font(extra_px * s)
        _draw_text_block(
            draw, _wrap(draw, extra, extra_font, max_w, extra_lines), extra_font, x, y, gap, max_y=max_y
        )


def _render_medium(url, title, subtitle, size: LabelSize) -> Image.Image:
    """QR uses the full printable height; number + name sit beside it, rotated 180°."""
    img = Image.new("RGB", (size.width_px, size.height_px), "white")
    pad = mm_to_px(MARGIN_MEDIUM_MM)
    qr_box = size.height_px - 2 * pad
    gap = mm_to_px(2.0)
    _paste_qr(img, url, qr_box, (pad, pad))
    col_x = pad + qr_box + gap
    col_w = size.width_px - col_x - pad
    col_h = qr_box
    if col_w > 4 and col_h > 4:
        strip = _sharp_text_image(
            col_h,
            col_w,
            lambda draw, s: _paint_medium_spine(draw, s, col_h, col_w, title, subtitle),
        )
        # Paint along the QR height, flip 180°, then stand the strip beside the QR.
        placed = strip.rotate(180, fillcolor="white").rotate(-90, expand=True, fillcolor="white")
        img.paste(placed, (col_x, pad))
    return img


def _paint_medium_spine(draw, s, width, height, title, subtitle):
    number = subtitle or title
    name = title if title and title != number else ""
    inset = max(s, _px(0.3, s))
    max_w = width * s - 2 * inset
    max_h = height * s - 2 * inset
    if name:
        num_font = _fit_font(number, max_w, int(max_h * 0.55), bold=True, min_px=max(8, 10 * s))
        name_font = _fit_font("Hg", max_w, int(max_h * 0.34), bold=False, min_px=max(8, 8 * s))
        num = number
        label = _ellipsize(draw, name, name_font, max_w)
        nb = draw.textbbox((0, 0), num, font=num_font)
        nmb = draw.textbbox((0, 0), label, font=name_font)
        gap = max(s, _px(0.35, s))
        block = (nb[3] - nb[1]) + gap + (nmb[3] - nmb[1])
        y0 = inset + max(0, (max_h - block) // 2)
        draw.text((inset, y0 - nb[1]), num, font=num_font, fill=0)
        y1 = y0 + (nb[3] - nb[1]) + gap
        draw.text((inset, y1 - nmb[1]), label, font=name_font, fill=0)
    else:
        num_font = _fit_font(number, max_w, int(max_h * 0.92), bold=True, min_px=max(8, 10 * s))
        nb = draw.textbbox((0, 0), number, font=num_font)
        y = inset + (max_h - (nb[3] - nb[1])) // 2 - nb[1]
        draw.text((inset, y), number, font=num_font, fill=0)


def _render_compact(url, title, subtitle, size: LabelSize) -> Image.Image:
    img = Image.new("RGB", (size.width_px, size.height_px), "white")
    pad = mm_to_px(MARGIN_COMPACT_MM)
    qr_box = size.height_px - 2 * pad
    _paste_qr(img, url, qr_box, (pad, pad))
    x = pad + qr_box + mm_to_px(1.5)
    text_w = size.width_px - x - pad
    text_h = qr_box
    if text_w > 4 and text_h > 4:
        img.paste(
            _sharp_text_image(
                text_w,
                text_h,
                lambda draw, s: _paint_number_name(draw, s, text_w, text_h, title, subtitle, 16, 13),
            ),
            (x, pad),
        )
    return img


def _paint_number_name(draw, s, width, height, title, subtitle, num_px, name_px):
    number = subtitle or title
    inset = s
    max_w = width * s - 2 * inset
    max_y = height * s - inset
    y = inset
    num_font = _fit_font(number, max_w, num_px * s, bold=True, min_px=max(8, 8 * s))
    num = _ellipsize(draw, number, num_font, max_w)
    draw.text((inset, y), num, font=num_font, fill=0)
    bbox = draw.textbbox((inset, y), num, font=num_font)
    y = bbox[3] + 2 * s
    if title and title != number and y + 10 * s < max_y:
        name_font = _font(name_px * s)
        for line in _wrap(draw, title, name_font, max_w, 2):
            bbox = draw.textbbox((inset, y), line, font=name_font)
            if bbox[3] > max_y:
                break
            draw.text((inset, y), line, font=name_font, fill=0)
            y = bbox[3] + s


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
    tab_inset = mm_to_px(1.0)
    tab_y = (body_h - tab_h) // 2
    draw.rectangle(
        [
            body_w + tab_inset,
            tab_y + tab_inset,
            body_w + tab_w - 1 - tab_inset,
            tab_y + tab_h - 1 - tab_inset,
        ],
        outline=0,
        width=1,
    )
    return canvas


def _cable_face(url: str, title: str, number: str, width: int, height: int) -> Image.Image:
    face = Image.new("RGB", (width, height), "white")
    pad = mm_to_px(MARGIN_CABLE_MM)
    qr_box = min(height - 2 * pad, mm_to_px(11))
    _paste_qr(face, url, qr_box, (pad, (height - qr_box) // 2))
    x = pad + qr_box + mm_to_px(1)
    text_w = width - x - pad
    text_h = height - 2 * pad
    if text_w > 4 and text_h > 4:
        face.paste(
            _sharp_text_image(
                text_w,
                text_h,
                lambda draw, s: _paint_number_name(draw, s, text_w, text_h, title, number, 12, 11),
            ),
            (x, pad),
        )
    return face


def png_filename(stem: str, size: LabelSize) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    return f"{safe}-{size.key}.png"
