"""stderr logging that systemd maps to journal priorities."""
import logging

_JOURNAL_PREFIX = {
    logging.CRITICAL: "<2>",
    logging.ERROR: "<3>",
    logging.WARNING: "<4>",
    logging.INFO: "<6>",
    logging.DEBUG: "<7>",
}


class JournalStreamHandler(logging.StreamHandler):
    """Prefix records so journald ``SyslogLevelPrefix`` sets the priority."""

    def format(self, record):
        prefix = _JOURNAL_PREFIX.get(record.levelno, "<6>")
        return prefix + super().format(record)
