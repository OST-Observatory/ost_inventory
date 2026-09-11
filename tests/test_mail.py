import logging
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.test import SimpleTestCase

from config.journal import JournalStreamHandler
from config.mail import (
    CONSOLE_BACKEND,
    SENDMAIL_BACKEND,
    SMTP_BACKEND,
    SendmailEmailBackend,
    resolve_email_backend,
)


class EmailBackendResolveTests(SimpleTestCase):
    def test_auto_console_without_host(self):
        self.assertEqual(resolve_email_backend("", ""), CONSOLE_BACKEND)
        self.assertEqual(resolve_email_backend("  ", "  "), CONSOLE_BACKEND)

    def test_auto_smtp_when_host_set(self):
        self.assertEqual(resolve_email_backend("", "mail.example.edu"), SMTP_BACKEND)

    def test_explicit_methods(self):
        self.assertEqual(resolve_email_backend("console", "mail.example.edu"), CONSOLE_BACKEND)
        self.assertEqual(resolve_email_backend("SMTP", ""), SMTP_BACKEND)
        self.assertEqual(resolve_email_backend("sendmail", ""), SENDMAIL_BACKEND)

    def test_rejects_unknown_method(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_email_backend("graph", "")


class SendmailBackendTests(SimpleTestCase):
    def test_pipes_message_to_sendmail(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mail.eml"
            wrapper = Path(tmp) / "wrapper"
            wrapper.write_text(f"#!/bin/sh\ncat > '{out}'\n", encoding="utf-8")
            wrapper.chmod(0o755)
            backend = SendmailEmailBackend(sendmail_path=str(wrapper))
            sent = backend.send_messages(
                [
                    EmailMessage(
                        "Subject",
                        "Body",
                        "from@example.com",
                        ["to@example.com"],
                    )
                ]
            )
            self.assertEqual(sent, 1)
            raw = out.read_bytes()
            self.assertIn(b"to@example.com", raw)
            self.assertIn(b"Subject", raw)

    def test_raises_when_sendmail_fails(self):
        backend = SendmailEmailBackend(sendmail_path="/bin/false")
        with self.assertRaises(OSError):
            backend.send_messages(
                [
                    EmailMessage(
                        "Subject",
                        "Body",
                        "from@example.com",
                        ["to@example.com"],
                    )
                ]
            )

    def test_skips_message_without_recipients(self):
        backend = SendmailEmailBackend(sendmail_path="/bin/false")
        self.assertEqual(backend.send_messages([EmailMessage("S", "B", "from@example.com", [])]), 0)


class JournalHandlerTests(SimpleTestCase):
    def test_prefixes_priority(self):
        handler = JournalStreamHandler()
        record = logging.LogRecord(
            "inventory", logging.WARNING, __file__, 1, "boom", (), None
        )
        self.assertTrue(handler.format(record).startswith("<4>"))
