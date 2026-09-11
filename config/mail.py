"""Email backend selection and a local sendmail pipe."""
import subprocess

from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
SENDMAIL_BACKEND = "config.mail.SendmailEmailBackend"

_BACKENDS = {
    "console": CONSOLE_BACKEND,
    "smtp": SMTP_BACKEND,
    "sendmail": SENDMAIL_BACKEND,
}


def resolve_email_backend(method: str, email_host: str) -> str:
    """Pick a Django EMAIL_BACKEND from EMAIL_METHOD and EMAIL_HOST.

    Empty method: SMTP when EMAIL_HOST is set, otherwise console (development).
    Explicit ``smtp`` with an empty host uses localhost (local MTA).
    """
    chosen = (method or "").strip().lower()
    if not chosen:
        chosen = "smtp" if (email_host or "").strip() else "console"
    backend = _BACKENDS.get(chosen)
    if backend is None:
        allowed = ", ".join(sorted(_BACKENDS))
        raise ImproperlyConfigured(
            f"EMAIL_METHOD must be one of {allowed}, not {method!r}."
        )
    return backend


class SendmailEmailBackend(BaseEmailBackend):
    """Hand messages to a local MTA via ``sendmail -i -t`` (no shell)."""

    def __init__(self, sendmail_path=None, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        from django.conf import settings

        self.sendmail_path = sendmail_path or getattr(
            settings, "EMAIL_SENDMAIL", "/usr/sbin/sendmail"
        )

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            if self._send(message):
                sent += 1
        return sent

    def _send(self, message):
        if not message.recipients():
            return False
        payload = message.message().as_bytes(linesep="\r\n")
        try:
            proc = subprocess.run(
                [self.sendmail_path, "-i", "-t"],
                input=payload,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            if not self.fail_silently:
                raise
            return False
        if proc.returncode != 0:
            if not self.fail_silently:
                err = proc.stderr.decode("utf-8", errors="replace").strip()
                raise OSError(err or f"sendmail exited {proc.returncode}")
            return False
        return True
