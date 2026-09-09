"""Fail-closed production checks (F-01)."""
from django.core.exceptions import ImproperlyConfigured

ALLOWED_DJANGO_ENVS = frozenset({"production", "development"})

INSECURE_SECRET_KEYS = frozenset(
    {
        "change-me-in-production-use-a-long-random-string",
        "dev-only-insecure-secret-key-change-me",
    }
)

MIN_SECRET_KEY_LENGTH = 50


def normalize_django_env(value: str) -> str:
    env = (value or "").strip().lower()
    if env not in ALLOWED_DJANGO_ENVS:
        raise ImproperlyConfigured(
            "DJANGO_ENV must be 'production' or 'development', "
            f"not {value!r}."
        )
    return env


def is_insecure_secret_key(secret_key: str) -> bool:
    key = (secret_key or "").strip()
    if len(key) < MIN_SECRET_KEY_LENGTH:
        return True
    return key in INSECURE_SECRET_KEYS


def validate_production_settings(*, secret_key, debug, allowed_hosts, databases):
    if debug:
        raise ImproperlyConfigured("DEBUG must be False in production.")
    if is_insecure_secret_key(secret_key):
        raise ImproperlyConfigured(
            "SECRET_KEY is missing, too short, or a known development placeholder."
        )
    hosts = [h for h in (allowed_hosts or []) if str(h).strip()]
    if not hosts:
        raise ImproperlyConfigured("ALLOWED_HOSTS must be non-empty in production.")
    engine = (databases or {}).get("default", {}).get("ENGINE", "")
    if engine != "django.db.backends.postgresql":
        raise ImproperlyConfigured("Production database engine must be PostgreSQL.")


def ldap_tls_is_required(server_uri: str, start_tls: bool, django_env: str) -> None:
    """Raise if production LDAP would send credentials in the clear."""
    if (django_env or "").lower() != "production":
        return
    uri = (server_uri or "").strip().lower()
    if not uri:
        return
    if uri.startswith("ldaps://"):
        return
    if uri.startswith("ldap://") and start_tls:
        return
    raise ImproperlyConfigured(
        "Production LDAP requires ldaps:// or LDAP_START_TLS=True; "
        "cleartext ldap:// is not allowed."
    )
