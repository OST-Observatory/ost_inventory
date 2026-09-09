"""Authenticated media delivery (F-04)."""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.static import serve

from accounts.permissions import read_required


def _safe_media_path(relative: str) -> Path:
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise Http404("Invalid path") from exc
    if not candidate.is_file():
        raise Http404("Not found")
    return candidate


@read_required
def protected_media(request, path):
    media_path = _safe_media_path(path)
    if getattr(settings, "DEBUG", False):
        return serve(request, path, document_root=settings.MEDIA_ROOT)

    sendfile_header = getattr(settings, "MEDIA_X_SENDFILE_HEADER", "")
    if sendfile_header:
        response = HttpResponse()
        response[sendfile_header] = str(media_path)
        return response

    return FileResponse(media_path.open("rb"), as_attachment=False)
