"""Photo upload helpers: UUID names, size/pixel limits, re-encode, strip EXIF.

Browsers reduce photos above PHOTO_MAX_BYTES before upload (static/app.js). As a
fallback, uploads up to PHOTO_MAX_UPLOAD_BYTES are re-encoded here until they fit.
"""
from io import BytesIO
from pathlib import Path
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError


def item_photo_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    now = timezone.now()
    return f"items/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"


JPEG_QUALITY = 85
JPEG_MIN_QUALITY = 55
MIN_REDUCED_DIMENSION = 640


def _encode(img, fmt, quality):
    buf = BytesIO()
    save_kwargs = {"format": fmt, "optimize": True}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
    img.save(buf, **save_kwargs)
    return buf


def process_item_photo(uploaded):
    """Validate and re-encode an uploaded image. Returns a new InMemoryUploadedFile.

    The result is at most PHOTO_MAX_BYTES; `was_reduced` on it tells whether
    quality or size had to be lowered below the normal re-encode to get there.
    """
    max_bytes = getattr(settings, "PHOTO_MAX_BYTES", 5 * 1024 * 1024)
    max_upload = getattr(settings, "PHOTO_MAX_UPLOAD_BYTES", 8 * 1024 * 1024)
    max_pixels = getattr(settings, "PHOTO_MAX_PIXELS", 20_000_000)
    max_dim = getattr(settings, "PHOTO_MAX_DIMENSION", 4096)
    allowed = getattr(settings, "PHOTO_ALLOWED_FORMATS", frozenset({"JPEG", "PNG", "WEBP"}))

    size = getattr(uploaded, "size", None)
    if size is not None and size > max_upload:
        raise ValidationError(
            f"Photo is too large to upload (max {max_upload // (1024 * 1024)} MB)."
        )

    uploaded.seek(0)
    try:
        with Image.open(uploaded) as probe:
            probe.verify()
            fmt = (probe.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Invalid image file.") from exc

    if fmt not in allowed:
        raise ValidationError("Only JPEG, PNG, and WebP photos are allowed.")

    uploaded.seek(0)
    with Image.open(uploaded) as img:
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        if width * height > max_pixels:
            raise ValidationError("Image has too many pixels.")
        img.thumbnail((max_dim, max_dim))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            out_fmt = "PNG"
            content_type = "image/png"
            ext = ".png"
        else:
            img = img.convert("RGB")
            out_fmt = "JPEG"
            content_type = "image/jpeg"
            ext = ".jpg"
        quality = JPEG_QUALITY
        was_reduced = False
        buf = _encode(img, out_fmt, quality)
        while buf.getbuffer().nbytes > max_bytes:
            was_reduced = True
            if out_fmt == "JPEG" and quality > JPEG_MIN_QUALITY:
                quality -= 10
            elif max(img.size) > MIN_REDUCED_DIMENSION:
                width, height = img.size
                img = img.resize((round(width * 0.8), round(height * 0.8)), Image.LANCZOS)
            else:
                raise ValidationError("Photo is too large, even after reducing it.")
            buf = _encode(img, out_fmt, quality)

    buf.seek(0)
    name = f"{uuid.uuid4().hex}{ext}"
    processed = InMemoryUploadedFile(
        buf,
        field_name="photo",
        name=name,
        content_type=content_type,
        size=buf.getbuffer().nbytes,
        charset=None,
    )
    processed.was_reduced = was_reduced
    return processed


def delete_photo_file(name, storage):
    """Delete a stored item photo together with its easy-thumbnails variants."""
    if not name:
        return
    from easy_thumbnails.files import get_thumbnailer

    thumbnailer = get_thumbnailer(storage, relative_name=name)
    source_cache = thumbnailer.get_source_cache()
    if source_cache:
        for thumbnail in source_cache.thumbnails.all():
            thumbnailer.thumbnail_storage.delete(thumbnail.name)
        source_cache.delete()  # cascades to the thumbnail cache rows
    storage.delete(name)
