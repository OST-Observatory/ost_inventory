"""Production settings."""
import environ

env = environ.Env()

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DATABASE_NAME"),
        "USER": env("DATABASE_USER"),
        "PASSWORD": env("DATABASE_PASSWORD"),
        "HOST": env("DATABASE_HOST", default="localhost"),
        "PORT": env("DATABASE_PORT", default="5432"),
        "OPTIONS": {
            "sslmode": env("DATABASE_SSLMODE", default="prefer"),
        },
    }
}

_force = env("FORCE_SCRIPT_NAME", default="").strip()
FORCE_SCRIPT_NAME = _force or None
_script = (FORCE_SCRIPT_NAME or "").rstrip("/")
if _script == "/inventory":
    ROOT_URLCONF = "config.urls_subpath"
# Path-absolute URLs so photos/CSS do not resolve relative to /inventory/items/5/.
STATIC_URL = f"{_script}/static/" if _script else "/static/"
MEDIA_URL = f"{_script}/media/" if _script else "/media/"

CSRF_TRUSTED_ORIGINS = env.list("TRUSTED_ORIGIN", default=[])
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

_ldap_log_level = "DEBUG" if env.bool("LDAP_DEBUG", default=False) else "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "journal": {"format": "%(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "journal": {
            "class": "config.journal.JournalStreamHandler",
            "formatter": "journal",
        },
    },
    "root": {"handlers": ["journal"], "level": "WARNING"},
    "loggers": {
        "django.request": {
            "handlers": ["journal"],
            "level": "ERROR",
            "propagate": False,
        },
        "inventory": {"handlers": ["journal"], "level": "INFO", "propagate": False},
        "accounts": {"handlers": ["journal"], "level": "INFO", "propagate": False},
        "django_auth_ldap": {
            "handlers": ["journal"],
            "level": _ldap_log_level,
            "propagate": False,
        },
    },
}
