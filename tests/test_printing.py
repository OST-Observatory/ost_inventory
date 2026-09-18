import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image

from inventory.labels import DPI, LABEL_SIZES, render_label_png
from inventory.printing import (
    IPP_VERSION,
    OP_GET_PRINTER_ATTRIBUTES,
    OP_PRINT_JOB,
    PRINTHEAD_DOTS,
    PWG_HEADER_SIZE,
    PWG_SYNC,
    TAG_END,
    TAG_ENUM,
    TAG_INTEGER,
    TAG_JOB_ATTRS,
    TAG_OPERATION_ATTRS,
    TAG_PRINTER_ATTRS,
    TAG_KEYWORD,
    TAG_URI,
    TAG_CHARSET,
    TAG_LANGUAGE,
    TAG_TEXT,
    TAG_NAME,
    PrintError,
    _packbits_line,
    build_get_printer_attributes_request,
    build_print_job_request,
    ipp_get_printer_attributes,
    ipp_print_job,
    parse_ipp_response,
    png_to_pwg_raster,
)


def decode_pwg(doc: bytes):
    """Minimal PWG raster decoder: returns [(header, rows, width, height, stride)]."""
    assert doc[:4] == PWG_SYNC
    pos = 4
    pages = []
    while pos < len(doc):
        hdr = doc[pos : pos + PWG_HEADER_SIZE]
        pos += PWG_HEADER_SIZE
        width, height = struct.unpack_from(">II", hdr, 372)
        stride = struct.unpack_from(">I", hdr, 392)[0]
        rows = bytearray()
        while len(rows) < stride * height:
            repeat = doc[pos] + 1
            pos += 1
            line = bytearray()
            while len(line) < stride:
                control = doc[pos]
                pos += 1
                if control <= 127:
                    line.extend(bytes([doc[pos]]) * (control + 1))
                    pos += 1
                else:
                    n = 257 - control
                    line.extend(doc[pos : pos + n])
                    pos += n
            assert len(line) == stride, "run overflowed the line"
            rows.extend(bytes(line) * repeat)
        assert len(rows) == stride * height, "line repeat overflowed the page"
        pages.append((hdr, bytes(rows), width, height, stride))
    return pages


def expected_bits(png: bytes, rotate: int = 0):
    """Reference bitmap straight from Pillow: set bit = pixel darker than 128."""
    with Image.open(BytesIO(png)) as img:
        gray = img.convert("L")
    if rotate:
        gray = gray.rotate(rotate, expand=True)
    width, height = gray.size
    stride = (width + 7) // 8
    out = bytearray(stride * height)
    px = gray.load()
    for y in range(height):
        for x in range(width):
            if px[x, y] < 128:
                out[y * stride + x // 8] |= 0x80 >> (x % 8)
    return bytes(out), width, height


def _png(width, height, black_pixels=()):
    img = Image.new("RGB", (width, height), "white")
    for x, y in black_pixels:
        img.putpixel((x, y), (0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class PackBitsTests(SimpleTestCase):
    def test_repeat_runs_split_at_128(self):
        self.assertEqual(_packbits_line(b"\x00" * 300), bytes([127, 0, 127, 0, 43, 0]))

    def test_literal_run(self):
        self.assertEqual(_packbits_line(b"\x01\x02\x03"), bytes([254, 1, 2, 3]))

    def test_single_byte_is_a_repeat_of_one(self):
        self.assertEqual(_packbits_line(b"\x07"), bytes([0, 7]))

    def test_mixed(self):
        self.assertEqual(
            _packbits_line(b"\x01\x02\x03\x03\x03\x04"),
            bytes([255, 1, 2, 2, 3, 0, 4]),
        )


class PwgRasterTests(SimpleTestCase):
    def test_header_describes_a_40x30_label(self):
        size = LABEL_SIZES["40x30"]
        png = render_label_png("https://x.test/i/1/", "Cam", "#0001", "Lab", size)
        doc = png_to_pwg_raster([png])
        self.assertTrue(doc.startswith(PWG_SYNC))
        (hdr, rows, width, height, stride), = decode_pwg(doc)
        self.assertEqual(hdr[:9], b"PwgRaster")
        self.assertEqual((width, height), (size.width_px, size.height_px))
        self.assertEqual(struct.unpack_from(">II", hdr, 276), (DPI, DPI))
        self.assertEqual(struct.unpack_from(">III", hdr, 384), (1, 1, (width + 7) // 8))
        self.assertEqual(struct.unpack_from(">II", hdr, 396), (0, 3))  # chunky, K
        self.assertEqual(struct.unpack_from(">I", hdr, 420)[0], 1)
        self.assertEqual(struct.unpack_from(">I", hdr, 340)[0], 1)  # copies
        self.assertEqual(struct.unpack_from(">I", hdr, 452)[0], 1)  # page count
        self.assertTrue(hdr[1732:].startswith(b"om_40x30mm_40x30mm"))

    def test_bitmap_matches_png_pixel_for_pixel(self):
        for key in ("40x30", "30x20", "50x80"):
            size = LABEL_SIZES[key]
            png = render_label_png("https://x.test/i/1/", "Camera body", "#0042", "Lab / 2a", size)
            (hdr, rows, width, height, stride), = decode_pwg(png_to_pwg_raster([png]))
            ref, ref_w, ref_h = expected_bits(png)
            self.assertEqual((width, height), (ref_w, ref_h), key)
            self.assertEqual(rows, ref, f"{key} bitmap differs")
            self.assertTrue(any(rows), f"{key} raster is blank")

    def test_black_pixel_sets_bit_and_padding_is_clear(self):
        png = _png(13, 3, black_pixels=[(3, 1), (12, 2)])
        (hdr, rows, width, height, stride), = decode_pwg(png_to_pwg_raster([png]))
        self.assertEqual((width, height, stride), (13, 3, 2))
        self.assertEqual(rows[0:2], b"\x00\x00")
        self.assertEqual(rows[2:4], bytes([0x80 >> 3, 0x00]))
        self.assertEqual(rows[4:6], bytes([0x00, 0x80 >> 4]))

    def test_cable_flag_is_rotated_to_run_along_the_tape(self):
        size = LABEL_SIZES["cable-flag"]
        png = render_label_png("https://x.test/i/1/", "Cable", "#0007", "", size, code="barcode")
        with Image.open(BytesIO(png)) as img:
            self.assertGreater(img.width, PRINTHEAD_DOTS)
            self.assertGreater(img.width, img.height)
        (hdr, rows, width, height, stride), = decode_pwg(png_to_pwg_raster([png]))
        self.assertEqual((width, height), (size.height_px, size.width_px))
        self.assertLessEqual(width, PRINTHEAD_DOTS)
        ref, _w, _h = expected_bits(png, rotate=90)
        self.assertEqual(rows, ref)

    def test_large_label_is_not_rotated(self):
        size = LABEL_SIZES["50x80"]
        png = render_label_png("https://x.test/i/1/", "Scope", "#0003", "Dome", size)
        (hdr, rows, width, height, stride), = decode_pwg(png_to_pwg_raster([png]))
        self.assertEqual((width, height), (size.width_px, size.height_px))

    def test_multi_page_and_copies(self):
        pngs = [_png(8, 2, [(0, 0)]), _png(16, 2, [(15, 1)])]
        pages = decode_pwg(png_to_pwg_raster(pngs, copies=3))
        self.assertEqual(len(pages), 2)
        for hdr, rows, width, height, stride in pages:
            self.assertEqual(struct.unpack_from(">I", hdr, 340)[0], 3)
            self.assertEqual(struct.unpack_from(">I", hdr, 452)[0], 2)
        self.assertEqual(pages[0][2], 8)
        self.assertEqual(pages[1][2], 16)

    def test_rejects_empty_and_bad_copies(self):
        with self.assertRaises(PrintError):
            png_to_pwg_raster([])
        with self.assertRaises(PrintError):
            png_to_pwg_raster([_png(8, 8)], copies=0)


def _ipp_attr(tag, name, value):
    if isinstance(value, int):
        payload = struct.pack(">i", value)
    else:
        payload = value.encode("utf-8")
    name_b = name.encode()
    return struct.pack(">BH", tag, len(name_b)) + name_b + struct.pack(">H", len(payload)) + payload


def _ipp_response(status, request_id, job_id=42, job_state=3, extra=b""):
    body = bytearray(struct.pack(">BBHI", 2, 0, status, request_id))
    body.append(TAG_OPERATION_ATTRS)
    body += _ipp_attr(TAG_CHARSET, "attributes-charset", "utf-8")
    body += _ipp_attr(TAG_LANGUAGE, "attributes-natural-language", "en")
    if status >= 0x0400:
        body += _ipp_attr(TAG_TEXT, "status-message", "printer says no")
    if job_id is not None:
        body.append(TAG_JOB_ATTRS)
        body += _ipp_attr(TAG_INTEGER, "job-id", job_id)
        body += _ipp_attr(TAG_ENUM, "job-state", job_state)
        body += _ipp_attr(TAG_KEYWORD, "job-state-reasons", "job-incoming")
        body += _ipp_attr(TAG_KEYWORD, "", "job-data-insufficient")
    body += extra
    body.append(TAG_END)
    return bytes(body)


class IppEncodingTests(SimpleTestCase):
    def test_print_job_request_layout(self):
        req = build_print_job_request(
            "ipp://p.test:8631/ipp/print/t50",
            request_id=7,
            user_name="writer",
            job_name="OST labels",
            document_format="image/pwg-raster",
            copies=2,
        )
        self.assertEqual(req[:8], struct.pack(">BBHI", IPP_VERSION[0], IPP_VERSION[1], OP_PRINT_JOB, 7))
        self.assertEqual(req[8], TAG_OPERATION_ATTRS)
        self.assertIn(_ipp_attr(TAG_URI, "printer-uri", "ipp://p.test:8631/ipp/print/t50"), req)
        self.assertIn(_ipp_attr(TAG_NAME, "requesting-user-name", "writer"), req)
        self.assertIn(b"image/pwg-raster", req)
        self.assertIn(bytes([TAG_JOB_ATTRS]) + _ipp_attr(TAG_INTEGER, "copies", 2), req)
        self.assertEqual(req[-1], TAG_END)

    def test_single_copy_omits_job_group(self):
        req = build_print_job_request(
            "ipp://p.test/ipp/print", request_id=1, user_name="u", job_name="j",
            document_format="image/pwg-raster", copies=1,
        )
        self.assertNotIn(b"copies", req)

    def test_get_printer_attributes_request(self):
        req = build_get_printer_attributes_request("ipp://p.test/ipp/print", request_id=3)
        self.assertEqual(struct.unpack(">H", req[2:4])[0], OP_GET_PRINTER_ATTRIBUTES)
        self.assertIn(b"requested-attributes", req)
        self.assertIn(b"media-ready", req)

    def test_parse_response_with_additional_values(self):
        resp = parse_ipp_response(_ipp_response(0x0000, 9))
        self.assertTrue(resp.ok)
        self.assertEqual(resp.request_id, 9)
        self.assertEqual(resp.first("job-id"), 42)
        self.assertEqual(resp.first("job-state"), 3)
        self.assertEqual(resp.all("job-state-reasons"), ["job-incoming", "job-data-insufficient"])
        self.assertEqual(resp.first("attributes-charset"), "utf-8")

    def test_parse_rejects_short_response(self):
        with self.assertRaises(PrintError):
            parse_ipp_response(b"\x02\x00")


class _FakeIppHandler(BaseHTTPRequestHandler):
    status = 0x0000
    content_type = "application/ipp"
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append((self.path, dict(self.headers), body))
        request_id = struct.unpack(">I", body[4:8])[0]
        op = struct.unpack(">H", body[2:4])[0]
        if op == OP_GET_PRINTER_ATTRIBUTES:
            extra = bytes([TAG_PRINTER_ATTRS])
            extra += _ipp_attr(TAG_NAME, "printer-name", "t50")
            extra += _ipp_attr(TAG_ENUM, "printer-state", 3)
            extra += _ipp_attr(TAG_KEYWORD, "document-format-supported", "image/pwg-raster")
            extra += _ipp_attr(TAG_KEYWORD, "", "image/jpeg")
            payload = _ipp_response(self.status, request_id, job_id=None, extra=extra)
        else:
            payload = _ipp_response(self.status, request_id)
        self.send_response(200)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence the test log
        pass


class IppTransportTests(SimpleTestCase):
    def setUp(self):
        _FakeIppHandler.status = 0x0000
        _FakeIppHandler.content_type = "application/ipp"
        _FakeIppHandler.received = []
        self.server = HTTPServer(("127.0.0.1", 0), _FakeIppHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        self.uri = f"ipp://127.0.0.1:{port}/ipp/print/t50"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_print_job_round_trip(self):
        doc = png_to_pwg_raster([_png(8, 8, [(1, 1)])])
        result = ipp_print_job(
            self.uri, doc, job_name="OST test", user_name="writer", copies=2, timeout=5
        )
        self.assertEqual(result.job_id, 42)
        self.assertEqual(result.job_state, "pending")
        path, headers, body = _FakeIppHandler.received[0]
        self.assertEqual(path, "/ipp/print/t50")
        self.assertEqual(headers["Content-Type"], "application/ipp")
        self.assertTrue(body.endswith(doc))
        self.assertIn(self.uri.encode(), body)
        self.assertIn(_ipp_attr(TAG_INTEGER, "copies", 2), body)

    def test_rejected_job_raises(self):
        _FakeIppHandler.status = 0x0507  # server-error-not-accepting-jobs
        with self.assertRaises(PrintError) as ctx:
            ipp_print_job(self.uri, b"RaS2", timeout=5)
        self.assertIn("0x0507", str(ctx.exception))
        self.assertIn("printer says no", str(ctx.exception))

    def test_non_ipp_reply_raises(self):
        _FakeIppHandler.content_type = "text/html"
        with self.assertRaises(PrintError):
            ipp_print_job(self.uri, b"RaS2", timeout=5)

    def test_get_printer_attributes(self):
        resp = ipp_get_printer_attributes(self.uri, timeout=5)
        self.assertEqual(resp.first("printer-name"), "t50")
        self.assertEqual(resp.first("printer-state"), 3)
        self.assertEqual(resp.all("document-format-supported"), ["image/pwg-raster", "image/jpeg"])

    def test_unreachable_printer_raises(self):
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(PrintError):
            ipp_print_job(self.uri, b"RaS2", timeout=2)

    def test_bad_scheme_raises(self):
        with self.assertRaises(PrintError):
            ipp_print_job("ftp://x/", b"RaS2")
        with self.assertRaises(PrintError):
            ipp_print_job("ipp:///no-host", b"RaS2")
