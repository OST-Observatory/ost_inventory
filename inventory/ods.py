"""Minimal ODS (OpenDocument spreadsheet) writer — no extra dependency."""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

_MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"

_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""


def _cell(value: str) -> str:
    return (
        '<table:table-cell office:value-type="string">'
        f"<text:p>{escape(value)}</text:p>"
        "</table:table-cell>"
    )


def spreadsheet_bytes(headers: list[str], rows: list[list[str]], sheet_name: str = "labels") -> bytes:
    body_rows = []
    for row in (headers, *rows):
        cells = "".join(_cell(str(col)) for col in row)
        body_rows.append(f"<table:table-row>{cells}</table:table-row>")
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  office:version="1.2">
  <office:body>
    <office:spreadsheet>
      <table:table table:name="{escape(sheet_name)}">
        {"".join(body_rows)}
      </table:table>
    </office:spreadsheet>
  </office:body>
</office:document-content>
"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", _MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", _MANIFEST)
        zf.writestr("content.xml", content)
    return buf.getvalue()
