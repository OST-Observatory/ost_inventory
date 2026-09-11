from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Probe LDAP connectivity and optional user lookup (no password check)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="",
            help="uid to search (does not attempt a user bind)",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        uri = getattr(settings, "AUTH_LDAP_SERVER_URI", "") or ""
        if not uri:
            raise CommandError("LDAP_SERVER_URI is empty; LDAP is not configured.")

        backends = getattr(settings, "AUTHENTICATION_BACKENDS", ())
        ldap_on = "django_auth_ldap.backend.LDAPBackend" in backends
        self.stdout.write(f"URI: {uri}")
        self.stdout.write(f"STARTTLS: {bool(getattr(settings, 'AUTH_LDAP_START_TLS', False))}")
        self.stdout.write(f"LDAPBackend enabled: {ldap_on}")
        if not ldap_on:
            raise CommandError(
                "LDAPBackend is not in AUTHENTICATION_BACKENDS. "
                "Check the journal for 'LDAP configuration failed'."
            )

        try:
            import ldap
            from ldap.filter import escape_filter_chars
        except ImportError as exc:
            raise CommandError("python-ldap is not installed") from exc

        from accounts.ldap_setup import bind_ldap_connection

        conn = bind_ldap_connection(
            ldap,
            uri,
            start_tls=bool(getattr(settings, "AUTH_LDAP_START_TLS", False)),
            bind_dn=getattr(settings, "AUTH_LDAP_BIND_DN", "") or "",
            bind_password=getattr(settings, "AUTH_LDAP_BIND_PASSWORD", "") or "",
            cacert=getattr(settings, "AUTH_LDAP_TLS_CACERT", "") or "",
            connect_timeout=getattr(settings, "AUTH_LDAP_CONNECT_TIMEOUT", 5),
        )
        if conn is None:
            raise CommandError(
                "Connect/bind failed. See journalctl -u ost-inventory "
                "for STARTTLS or bind errors."
            )
        self.stdout.write("Connect and bind: ok")

        username = (options.get("username") or "").strip()
        if not username:
            conn.unbind_s()
            self.stdout.write("Pass --username to search a uid.")
            return

        base = getattr(settings, "AUTH_LDAP_USER_SEARCH_BASE", "") or ""
        raw_filter = getattr(settings, "AUTH_LDAP_USER_FILTER", "(uid=%(user)s)")
        ldap_filter = raw_filter.replace("%(user)s", escape_filter_chars(username))
        if not base:
            conn.unbind_s()
            raise CommandError("LDAP_USER_SEARCH_BASE is empty.")
        try:
            results = conn.search_s(base, ldap.SCOPE_SUBTREE, ldap_filter, ["uid"])
        except ldap.LDAPError as exc:
            conn.unbind_s()
            raise CommandError(f"User search failed: {exc}") from exc

        if not results:
            conn.unbind_s()
            raise CommandError(
                f"No entry for uid={username!r} under {base} with {ldap_filter}."
            )
        dn, attrs = results[0]
        self.stdout.write(f"User DN: {dn}")

        uid_str = username
        for raw in attrs.get("uid") or []:
            uid_str = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
            break

        group_dns = [
            getattr(settings, "LDAP_GROUP_STUDENT_DN", "") or "",
            getattr(settings, "LDAP_GROUP_SUPERVISOR_DN", "") or "",
            getattr(settings, "LDAP_GROUP_STAFF_DN", "") or "",
            getattr(settings, "LDAP_GROUP_SUPERUSER_DN", "") or "",
        ]
        for group_dn in group_dns:
            if not group_dn:
                continue
            try:
                gres = conn.search_s(
                    group_dn, ldap.SCOPE_BASE, "(objectClass=*)", ["member", "memberUid", "objectClass"]
                )
            except ldap.LDAPError as exc:
                self.stdout.write(f"Group {group_dn}: read failed ({exc})")
                continue
            if not gres:
                self.stdout.write(f"Group {group_dn}: not found")
                continue
            _, gattrs = gres[0]
            members = [
                (m.decode() if isinstance(m, (bytes, bytearray)) else str(m))
                for m in (gattrs.get("member") or [])
            ]
            member_uids = [
                (m.decode() if isinstance(m, (bytes, bytearray)) else str(m))
                for m in (gattrs.get("memberUid") or [])
            ]
            in_member = any(m.lower() == dn.lower() for m in members)
            in_uid = uid_str in member_uids
            self.stdout.write(
                f"Group {group_dn}: member={in_member} memberUid={in_uid}"
            )
            if not in_member and in_uid:
                self.stdout.write(
                    "  Note: django-auth-ldap REQUIRE_GROUP uses groupOfNames "
                    "member, not memberUid. Login can fail even if memberUid matches."
                )
        conn.unbind_s()
