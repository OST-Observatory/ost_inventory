"""Photo upload helpers: UUID names, size/pixel limits, re-encode, strip EXIF."""
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


def process_item_photo(uploaded):
    """Validate and re-encode an uploaded image. Returns a new InMemoryUploadedFile."""
    max_bytes = getattr(settings, "PHOTO_MAX_BYTES", 5 * 1024 * 1024)
    max_pixels = getattr(settings, "PHOTO_MAX_PIXELS", 20_000_000)
    max_dim = getattr(settings, "PHOTO_MAX_DIMENSION", 4096)
    allowed = getattr(settings, "PHOTO_ALLOWED_FORMATS", frozenset({"JPEG", "PNG", "WEBP"}))

    size = getattr(uploaded, "size", None)
    if size is not None and size > max_bytes:
        raise ValidationError("Photo is too large (max 5 MB).")

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
        buf = BytesIO()
        save_kwargs = {"format": out_fmt, "optimize": True}
        if out_fmt == "JPEG":
            save_kwargs["quality"] = 85
        img.save(buf, **save_kwargs)

    buf.seek(0)
    name = f"{uuid.uuid4().hex}{ext}"
    return InMemoryUploadedFile(
        buf,
        field_name="photo",
        name=name,
        content_type=content_type,
        size=buf.getbuffer().nbytes,
        charset=None,
    )
