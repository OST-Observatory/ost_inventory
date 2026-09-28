"""Deactivate accounts whose entry has been removed from the observatory LDAP.

Django keeps the name and e-mail address copied from LDAP after someone leaves, and the account
cannot be deleted (items, loans and stocktakes reference it with PROTECT). Such accounts are
deactivated and lose first name, last name and e-mail; the username stays so that the history
remains readable. Stated in the central privacy policy (landing page, #inventory).

Only accounts provisioned by LDAP are considered (no usable local password), so local emergency
admins are never touched. Any LDAP error aborts the run without changes: django-auth-ldap's own
helpers report errors as "user not found", which would deactivate everyone during an outage.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

# Refuse mass deactivation (wrong search base, changed filter …) unless forced.
SAFETY_MIN_ACCOUNTS = 3
SAFETY_MAX_FRACTION = 0.5


class LdapUnavailable(Exception):
    """LDAP is not configured or cannot be queried; nothing was changed."""


class SafetyStop(Exception):
    """Too many accounts would be deactivated at once; nothing was changed."""


@dataclass
class DepartedResult:
    checked: int = 0
    departed: list[str] = field(default_factory=list)
    applied: bool = False


def ldap_configured() -> bool:
    return bool(getattr(settings, "AUTH_LDAP_SERVER_URI", "")) and hasattr(
        settings, "AUTH_LDAP_USER_SEARCH"
    )


@contextmanager
def ldap_entry_lookup():
    """Yield ``exists(username) -> bool``; raises LdapUnavailable on any connect/search error."""
    if not ldap_configured():
        raise LdapUnavailable("LDAP is not configured (LDAP_SERVER_URI / LDAP_USER_SEARCH_BASE)")
    import ldap
    from ldap.filter import escape_filter_chars

    from accounts.ldap_setup import bind_ldap_connection

    conn = bind_ldap_connection(
        ldap,
        settings.AUTH_LDAP_SERVER_URI,
        start_tls=bool(getattr(settings, "AUTH_LDAP_START_TLS", False)),
        bind_dn=getattr(settings, "AUTH_LDAP_BIND_DN", "") or "",
        bind_password=getattr(settings, "AUTH_LDAP_BIND_PASSWORD", "") or "",
        cacert=getattr(settings, "AUTH_LDAP_TLS_CACERT", "") or "",
        connect_timeout=getattr(settings, "AUTH_LDAP_CONNECT_TIMEOUT", 5),
    )
    if conn is None:
        raise LdapUnavailable("LDAP connect/bind failed (see log)")
    search = settings.AUTH_LDAP_USER_SEARCH

    def exists(username: str) -> bool:
        filterstr = search.filterstr % {"user": escape_filter_chars(username)}
        try:
            results = conn.search_s(search.base_dn, search.scope, filterstr, ["1.1"])
        except ldap.LDAPError as exc:
            raise LdapUnavailable(f"LDAP search failed: {exc}") from exc
        return any(dn for dn, _attrs in results)  # referrals come back with dn None

    try:
        yield exists
    finally:
        try:
            conn.unbind_s()
        except Exception:
            pass


def ldap_provisioned_active_users():
    User = get_user_model()
    return [u for u in User.objects.filter(is_active=True) if not u.has_usable_password()]


def deactivate_departed_users(exists, *, dry_run: bool = False, force: bool = False) -> DepartedResult:
    """Check every active LDAP account with ``exists`` and deactivate the ones that are gone."""
    users = ldap_provisioned_active_users()
    result = DepartedResult(checked=len(users))
    result.departed = [u.get_username() for u in users if not exists(u.get_username())]

    too_many = (
        len(result.departed) > SAFETY_MIN_ACCOUNTS
        and len(result.departed) > SAFETY_MAX_FRACTION * len(users)
    )
    if too_many and not force:
        raise SafetyStop(
            f"{len(result.departed)} of {len(users)} LDAP accounts not found — check "
            "LDAP_USER_SEARCH_BASE / LDAP_USER_FILTER; rerun with --force if this is correct"
        )

    if result.departed and not dry_run:
        User = get_user_model()
        User.objects.filter(
            **{f"{User.USERNAME_FIELD}__in": result.departed}, is_active=True
        ).update(is_active=False, first_name="", last_name="", email="")
        result.applied = True
        logger.info("Deactivated departed LDAP accounts: %s", ", ".join(result.departed))
    return result
