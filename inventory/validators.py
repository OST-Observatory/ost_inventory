"""Shared field validators."""
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def reject_newlines(value: str, field_label: str = "This field"):
    if value and ("\n" in value or "\r" in value):
        raise ValidationError(f"{field_label} must not contain line breaks.")


def validate_optional_email_or_text(value: str):
    """Allow blank/free text, but require a real email when '@' is present."""
    value = (value or "").strip()
    reject_newlines(value, "Contact")
    if "@" in value:
        try:
            validate_email(value)
        except ValidationError as exc:
            raise ValidationError("Enter a valid email address, or omit '@'.") from exc
    return value
