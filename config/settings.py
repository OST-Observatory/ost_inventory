"""Shared Django settings for ost_inventory."""
from pathlib import Path

import environ

from accounts.ldap_setup import configure_ldap_from_env
from config.mail import SMTP_BACKEND, resolve_email_backend
from config.security_checks import normalize_django_env, validate_production_settings

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECURE_SSL_REDIRECT=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DJANGO_ENV = normalize_django_env(env("DJANGO_ENV", default="development"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "easy_thumbnails",
    "import_export",
    "accounts",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.permissions",
                "inventory.context_processors.nav",
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inventory:search"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_AGE = 60 * 60 * 12

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

CSV_IMPORT_MAX_BYTES = 2 * 1024 * 1024
CSV_IMPORT_MAX_ROWS = 2000
CSV_IMPORT_MAX_FIELD_LENGTH = 500
CSV_IMPORT_MAX_LOCATION_DEPTH = 2

PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_MAX_PIXELS = 20_000_000
PHOTO_MAX_DIMENSION = 4096
PHOTO_ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW = 600
LOGIN_LOCKOUT_SECONDS = 900

THUMBNAIL_ALIASES = {
    "": {
        "list": {"size": (72, 72), "crop": True},
        "detail": {"size": (720, 720), "crop": False},
    },
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="inventory@localhost")
EMAIL_METHOD = env("EMAIL_METHOD", default="")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=30)
EMAIL_SENDMAIL = env("EMAIL_SENDMAIL", default="/usr/sbin/sendmail")
EMAIL_BACKEND = resolve_email_backend(EMAIL_METHOD, EMAIL_HOST)
if EMAIL_BACKEND == SMTP_BACKEND and not (EMAIL_HOST or "").strip():
    EMAIL_HOST = "localhost"

# LDAP env (configured only when LDAP_SERVER_URI is set)
AUTH_LDAP_SERVER_URI = env.str("LDAP_SERVER_URI", default="")
AUTH_LDAP_START_TLS = env.bool("LDAP_START_TLS", default=False)
AUTH_LDAP_BIND_DN = env.str("LDAP_BIND_DN", default="")
AUTH_LDAP_BIND_PASSWORD = env.str("LDAP_BIND_PASSWORD", default="")
AUTH_LDAP_USER_SEARCH_BASE = env.str("LDAP_USER_SEARCH_BASE", default="")
AUTH_LDAP_GROUP_SEARCH_BASE = env.str("LDAP_GROUP_SEARCH_BASE", default="")
AUTH_LDAP_CONNECT_TIMEOUT = env.int("LDAP_CONNECT_TIMEOUT", default=5)
AUTH_LDAP_USER_FILTER = (
    env.str("LDAP_USER_FILTER", default="").strip() or "(uid=%(user)s)"
)
AUTH_LDAP_TLS_CACERT = env.str("LDAP_TLS_CACERT", default="")
LDAP_GROUP_STAFF_DN = env.str("LDAP_GROUP_STAFF_DN", default="")
LDAP_GROUP_SUPERUSER_DN = env.str("LDAP_GROUP_SUPERUSER_DN", default="")
LDAP_GROUP_SUPERVISOR_DN = env.str("LDAP_GROUP_SUPERVISOR_DN", default="")
LDAP_GROUP_STUDENT_DN = env.str("LDAP_GROUP_STUDENT_DN", default="")

configure_ldap_from_env(globals(), env)

if DJANGO_ENV == "production":
    from .settings_production import *  # noqa: F401,F403
    validate_production_settings(
        secret_key=SECRET_KEY,
        debug=DEBUG,
        allowed_hosts=ALLOWED_HOSTS,
        databases=DATABASES,
    )
else:
    from .settings_development import *  # noqa: F401,F403
