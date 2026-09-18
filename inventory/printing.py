"""Direct label printing over IPP (pure Python, no CUPS client needed).

Two building blocks:

* :func:`png_to_pwg_raster` turns the 203 dpi label PNGs from
  :mod:`inventory.labels` into a 1-bit PWG raster document (PWG 5102.4). The
  bitmap is copied pixel for pixel, so the print matches the preview exactly.
* :func:`ipp_print_job` submits such a document to an IPP printer, for example
  ``supvan-printer-app`` (``ipp://host:8631/ipp/print/<name>``) or a CUPS queue.

The T50 printhead is 384 dots (48 mm) wide. Pages wider than that are cropped
symmetrically by the printer application; the 50 x 80 mm layout relies on that.
"""

from __future__ import annotations

import http.client
import struct
from dataclasses import dataclass, field
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image

from inventory.labels import DPI

# Dots across the T50 printhead (48 mm at 8 dots/mm).
PRINTHEAD_DOTS = 384

# Landscape pages wider than the head (the cable flag, 640 x 240) are rotated
# so that their short side runs across the head. Pillow rotates
# counter-clockwise, so +90 puts the right end of the PNG (the wrap tab) at the
# leading edge. Flip to -90 if the die-cut turns out to run the other way.
ROTATE_LANDSCAPE_DEGREES = 90

PWG_SYNC = b"RaS2"
PWG_HEADER_SIZE = 1796
PWG_MEDIA_CLASS = b"PwgRaster"
# cups_cspace_t: CUPS_CSPACE_K (1 = black ink)
CUPS_CSPACE_K = 3

PWG_RASTER_FORMAT = "image/pwg-raster"

# IPP (RFC 8010 / 8011)
IPP_VERSION = (2, 0)
OP_PRINT_JOB = 0x0002
OP_GET_PRINTER_ATTRIBUTES = 0x000B

TAG_OPERATION_ATTRS = 0x01
TAG_JOB_ATTRS = 0x02
TAG_END = 0x03
TAG_PRINTER_ATTRS = 0x04
TAG_UNSUPPORTED_ATTRS = 0x05

TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_OCTET_STRING = 0x30
TAG_DATETIME = 0x31
TAG_RESOLUTION = 0x32
TAG_RANGE = 0x33
TAG_BEG_COLLECTION = 0x34
TAG_TEXT_WITH_LANG = 0x35
TAG_NAME_WITH_LANG = 0x36
TAG_END_COLLECTION = 0x37
TAG_TEXT = 0x41
TAG_NAME = 0x42
TAG_KEYWORD = 0x44
TAG_URI = 0x45
TAG_URI_SCHEME = 0x46
TAG_CHARSET = 0x47
TAG_LANGUAGE = 0x48
TAG_MIME_TYPE = 0x49
TAG_MEMBER_NAME = 0x4A

_STRING_TAGS = {
    TAG_TEXT,
    TAG_NAME,
    TAG_KEYWORD,
    TAG_URI,
    TAG_URI_SCHEME,
    TAG_CHARSET,
    TAG_LANGUAGE,
    TAG_MIME_TYPE,
    TAG_MEMBER_NAME,
}

JOB_STATES = {
    3: "pending",
    4: "pending-held",
    5: "processing",
    6: "processing-stopped",
    7: "canceled",
    8: "aborted",
    9: "completed",
}

PRINTER_STATES = {3: "idle", 4: "processing", 5: "stopped"}

DEFAULT_IPP_PORT = 631
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class PrintError(Exception):
    """The job could not be handed to the printer."""


# --------------------------------------------------------------------------
# PWG raster
# --------------------------------------------------------------------------


def _to_bilevel(png: bytes) -> tuple[bytes, int, int]:
    """Decode a label PNG into MSB-first 1-bit rows where a set bit is black.

    Returns ``(rows, width, height)``; each row is ``ceil(width / 8)`` bytes.
    """
    with Image.open(BytesIO(png)) as img:
        gray = img.convert("L")
    if gray.width > gray.height and gray.width > PRINTHEAD_DOTS:
        gray = gray.rotate(ROTATE_LANDSCAPE_DEGREES, expand=True)
    # 1 = black so the printer application can burn the set bits as-is.
    bits = gray.point(lambda v: 255 if v < 128 else 0, mode="1")
    width, height = bits.size
    stride = (width + 7) // 8
    raw = bits.tobytes()
    if len(raw) != stride * height:  # pragma: no cover - Pillow invariant
        raise PrintError("unexpected bitmap size from Pillow")
    tail = width % 8
    if tail:
        mask = (0xFF << (8 - tail)) & 0xFF
        rows = bytearray(raw)
        for y in range(height):
            rows[y * stride + stride - 1] &= mask
        raw = bytes(rows)
    return raw, width, height


def _packbits_line(row: bytes) -> bytes:
    """PWG 5102.4 run-length coding of one line (pixel = one byte at 1 bpp)."""
    out = bytearray()
    i = 0
    n = len(row)
    while i < n:
        value = row[i]
        run = 1
        while i + run < n and row[i + run] == value and run < 128:
            run += 1
        if run >= 2:
            out.append(run - 1)
            out.append(value)
            i += run
            continue
        j = i + 1
        while j < n and j - i < 128 and not (j + 1 < n and row[j] == row[j + 1]):
            j += 1
        literal = row[i:j]
        if len(literal) == 1:
            out.append(0)
            out.append(literal[0])
        else:
            out.append(257 - len(literal))
            out.extend(literal)
        i = j
    return bytes(out)


def _compress_page(rows: bytes, stride: int, height: int) -> bytes:
    out = bytearray()
    y = 0
    while y < height:
        line = rows[y * stride : (y + 1) * stride]
        repeat = 1
        while (
            y + repeat < height
            and repeat < 256
            and rows[(y + repeat) * stride : (y + repeat + 1) * stride] == line
        ):
            repeat += 1
        out.append(repeat - 1)
        out.extend(_packbits_line(line))
        y += repeat
    return bytes(out)


def _pwg_header(width: int, height: int, stride: int, copies: int, page_count: int) -> bytes:
    hdr = bytearray(PWG_HEADER_SIZE)
    hdr[0 : len(PWG_MEDIA_CLASS)] = PWG_MEDIA_CLASS
    struct.pack_into(">II", hdr, 276, DPI, DPI)  # HWResolution
    struct.pack_into(">I", hdr, 340, copies)  # NumCopies
    width_pt = round(width * 72 / DPI)
    height_pt = round(height * 72 / DPI)
    struct.pack_into(">II", hdr, 352, width_pt, height_pt)  # PageSize
    struct.pack_into(">II", hdr, 372, width, height)  # cupsWidth, cupsHeight
    struct.pack_into(">III", hdr, 384, 1, 1, stride)  # BitsPerColor, BitsPerPixel, BytesPerLine
    struct.pack_into(">II", hdr, 396, 0, CUPS_CSPACE_K)  # ColorOrder chunky, ColorSpace
    struct.pack_into(">I", hdr, 420, 1)  # cupsNumColors
    struct.pack_into(">I", hdr, 452, page_count)  # TotalPageCount
    struct.pack_into(">I", hdr, 484, 4)  # PrintQuality normal
    width_mm = round(width * 25.4 / DPI)
    height_mm = round(height * 25.4 / DPI)
    name = f"om_{width_mm}x{height_mm}mm_{width_mm}x{height_mm}mm".encode("ascii")
    hdr[1732 : 1732 + len(name)] = name  # cupsPageSizeName
    return bytes(hdr)


def png_to_pwg_raster(pngs: list[bytes], *, copies: int = 1) -> bytes:
    """Build a multi-page 1-bit PWG raster document from label PNGs."""
    if not pngs:
        raise PrintError("No labels to print.")
    if copies < 1:
        raise PrintError("copies must be at least 1")
    out = bytearray(PWG_SYNC)
    for png in pngs:
        rows, width, height = _to_bilevel(png)
        stride = (width + 7) // 8
        out.extend(_pwg_header(width, height, stride, copies, len(pngs)))
        out.extend(_compress_page(rows, stride, height))
    return bytes(out)


# --------------------------------------------------------------------------
# IPP encoding / decoding
# --------------------------------------------------------------------------


def _attr(tag: int, name: str, value) -> bytes:
    if isinstance(value, str):
        payload = value.encode("utf-8")
    elif isinstance(value, bool):
        payload = b"\x01" if value else b"\x00"
    elif isinstance(value, int):
        payload = struct.pack(">i", value)
    else:
        payload = bytes(value)
    name_b = name.encode("utf-8")
    return struct.pack(">BH", tag, len(name_b)) + name_b + struct.pack(">H", len(payload)) + payload


def _attr_list(tag: int, name: str, values: list[str]) -> bytes:
    out = bytearray()
    for i, v in enumerate(values):
        out.extend(_attr(tag, name if i == 0 else "", v))
    return bytes(out)


def build_print_job_request(
    printer_uri: str,
    *,
    request_id: int,
    user_name: str,
    job_name: str,
    document_format: str,
    copies: int,
) -> bytes:
    req = bytearray(struct.pack(">BBHI", IPP_VERSION[0], IPP_VERSION[1], OP_PRINT_JOB, request_id))
    req.append(TAG_OPERATION_ATTRS)
    req.extend(_attr(TAG_CHARSET, "attributes-charset", "utf-8"))
    req.extend(_attr(TAG_LANGUAGE, "attributes-natural-language", "en"))
    req.extend(_attr(TAG_URI, "printer-uri", printer_uri))
    req.extend(_attr(TAG_NAME, "requesting-user-name", user_name[:255] or "inventory"))
    req.extend(_attr(TAG_NAME, "job-name", job_name[:255] or "label"))
    req.extend(_attr(TAG_MIME_TYPE, "document-format", document_format))
    if copies > 1:
        req.append(TAG_JOB_ATTRS)
        req.extend(_attr(TAG_INTEGER, "copies", copies))
    req.append(TAG_END)
    return bytes(req)


def build_get_printer_attributes_request(printer_uri: str, *, request_id: int) -> bytes:
    req = bytearray(
        struct.pack(">BBHI", IPP_VERSION[0], IPP_VERSION[1], OP_GET_PRINTER_ATTRIBUTES, request_id)
    )
    req.append(TAG_OPERATION_ATTRS)
    req.extend(_attr(TAG_CHARSET, "attributes-charset", "utf-8"))
    req.extend(_attr(TAG_LANGUAGE, "attributes-natural-language", "en"))
    req.extend(_attr(TAG_URI, "printer-uri", printer_uri))
    req.extend(
        _attr_list(
            TAG_KEYWORD,
            "requested-attributes",
            [
                "printer-name",
                "printer-info",
                "printer-make-and-model",
                "printer-state",
                "printer-state-reasons",
                "printer-is-accepting-jobs",
                "document-format-supported",
                "media-ready",
                "media-supported",
                "printer-resolution-supported",
            ],
        )
    )
    req.append(TAG_END)
    return bytes(req)


@dataclass
class IppResponse:
    version: tuple[int, int]
    status_code: int
    request_id: int
    groups: list[tuple[int, dict[str, list]]] = field(default_factory=list)

    def first(self, name: str, default=None):
        for _tag, attrs in self.groups:
            if name in attrs and attrs[name]:
                return attrs[name][0]
        return default

    def all(self, name: str) -> list:
        for _tag, attrs in self.groups:
            if name in attrs:
                return list(attrs[name])
        return []

    @property
    def ok(self) -> bool:
        return self.status_code < 0x0100

    @property
    def status_text(self) -> str:
        msg = self.first("status-message")
        return f"0x{self.status_code:04x}" + (f" ({msg})" if isinstance(msg, str) and msg else "")


def _decode_value(tag: int, raw: bytes):
    if tag in (TAG_INTEGER, TAG_ENUM) and len(raw) == 4:
        return struct.unpack(">i", raw)[0]
    if tag == TAG_BOOLEAN and len(raw) == 1:
        return bool(raw[0])
    if tag in _STRING_TAGS:
        return raw.decode("utf-8", errors="replace")
    if tag in (TAG_TEXT_WITH_LANG, TAG_NAME_WITH_LANG) and len(raw) >= 4:
        lang_len = struct.unpack(">H", raw[:2])[0]
        text_len_off = 2 + lang_len
        if len(raw) >= text_len_off + 2:
            text_len = struct.unpack(">H", raw[text_len_off : text_len_off + 2])[0]
            return raw[text_len_off + 2 : text_len_off + 2 + text_len].decode("utf-8", "replace")
    if tag == TAG_RESOLUTION and len(raw) == 9:
        x, y, unit = struct.unpack(">iiB", raw)
        return (x, y, unit)
    if tag == TAG_RANGE and len(raw) == 8:
        return struct.unpack(">ii", raw)
    return raw


def parse_ipp_response(data: bytes) -> IppResponse:
    if len(data) < 8:
        raise PrintError("IPP response too short")
    major, minor, status, request_id = struct.unpack(">BBHI", data[:8])
    resp = IppResponse((major, minor), status, request_id)
    pos = 8
    attrs: dict[str, list] | None = None
    last_name = None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == TAG_END:
            break
        if tag < 0x10:
            attrs = {}
            resp.groups.append((tag, attrs))
            last_name = None
            continue
        if pos + 2 > len(data):
            raise PrintError("truncated IPP attribute")
        name_len = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        name = data[pos : pos + name_len].decode("utf-8", errors="replace")
        pos += name_len
        if pos + 2 > len(data):
            raise PrintError("truncated IPP attribute")
        value_len = struct.unpack(">H", data[pos : pos + 2])[0]
        pos += 2
        raw = data[pos : pos + value_len]
        pos += value_len
        if attrs is None:
            attrs = {}
            resp.groups.append((TAG_OPERATION_ATTRS, attrs))
        if name_len == 0:
            if last_name is None:
                continue
            name = last_name
        else:
            last_name = name
        attrs.setdefault(name, []).append(_decode_value(tag, raw))
    return resp


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def _http_target(printer_uri: str) -> tuple[type, str, int, str]:
    parts = urlsplit(printer_uri)
    scheme = (parts.scheme or "").lower()
    if scheme in ("ipp", "http"):
        conn_cls = http.client.HTTPConnection
    elif scheme in ("ipps", "https"):
        conn_cls = http.client.HTTPSConnection
    else:
        raise PrintError(f"Unsupported printer URI scheme: {printer_uri!r}")
    if not parts.hostname:
        raise PrintError(f"Printer URI has no host: {printer_uri!r}")
    port = parts.port or DEFAULT_IPP_PORT
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return conn_cls, parts.hostname, port, path


def ipp_request(printer_uri: str, payload: bytes, *, timeout: float = 30.0) -> IppResponse:
    """POST one IPP message (request + optional document) and parse the reply."""
    conn_cls, host, port, path = _http_target(printer_uri)
    conn = conn_cls(host, port, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body=payload,
            headers={
                "Content-Type": "application/ipp",
                "Content-Length": str(len(payload)),
                "Connection": "close",
            },
        )
        resp = conn.getresponse()
        body = resp.read(MAX_RESPONSE_BYTES)
        status = resp.status
        ctype = resp.getheader("Content-Type", "")
    except (OSError, http.client.HTTPException) as exc:
        raise PrintError(f"Cannot reach printer at {host}:{port}: {exc}") from exc
    finally:
        conn.close()
    if status != 200:
        raise PrintError(f"Printer returned HTTP {status}")
    if "application/ipp" not in ctype.lower():
        raise PrintError(f"Printer returned {ctype or 'no content type'} instead of IPP")
    return parse_ipp_response(body)


@dataclass(frozen=True)
class IppJobResult:
    job_id: int | None
    job_state: str
    status_code: int


def ipp_print_job(
    printer_uri: str,
    document: bytes,
    *,
    document_format: str = PWG_RASTER_FORMAT,
    job_name: str = "label",
    user_name: str = "inventory",
    copies: int = 1,
    timeout: float = 30.0,
    request_id: int = 1,
) -> IppJobResult:
    """Submit ``document`` as an IPP Print-Job and return the accepted job."""
    head = build_print_job_request(
        printer_uri,
        request_id=request_id,
        user_name=user_name,
        job_name=job_name,
        document_format=document_format,
        copies=copies,
    )
    resp = ipp_request(printer_uri, head + document, timeout=timeout)
    if not resp.ok:
        raise PrintError(f"Printer rejected the job: {resp.status_text}")
    job_id = resp.first("job-id")
    state_code = resp.first("job-state")
    state = JOB_STATES.get(state_code, str(state_code)) if state_code is not None else "unknown"
    return IppJobResult(job_id if isinstance(job_id, int) else None, state, resp.status_code)


def ipp_get_printer_attributes(printer_uri: str, *, timeout: float = 30.0) -> IppResponse:
    resp = ipp_request(
        printer_uri,
        build_get_printer_attributes_request(printer_uri, request_id=1),
        timeout=timeout,
    )
    if not resp.ok:
        raise PrintError(f"Get-Printer-Attributes failed: {resp.status_text}")
    return resp
