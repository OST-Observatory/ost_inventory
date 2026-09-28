"""Accounts removed from LDAP are deactivated and lose name and e-mail."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.departed import LdapUnavailable, SafetyStop, deactivate_departed_users

User = get_user_model()


def _ldap_user(username):
    # LDAP-provisioned accounts have no usable local password.
    return User.objects.create_user(
        username=username, password=None, first_name="First", last_name="Last",
        email=f"{username}@example.org",
    )


class DeactivateDepartedTests(TestCase):
    def setUp(self):
        self.present = _ldap_user("present")
        self.gone = _ldap_user("gone")
        self.local_admin = User.objects.create_user(
            username="admin", password="local-pass", email="admin@example.org"
        )
        self.in_ldap = {"present"}

    def exists(self, username):
        return username in self.in_ldap

    def test_departed_account_is_deactivated_and_cleared(self):
        result = deactivate_departed_users(self.exists)

        self.assertEqual(result.departed, ["gone"])
        self.gone.refresh_from_db()
        self.assertFalse(self.gone.is_active)
        self.assertEqual((self.gone.first_name, self.gone.last_name, self.gone.email), ("", "", ""))
        self.assertEqual(self.gone.username, "gone")
        self.present.refresh_from_db()
        self.assertTrue(self.present.is_active)
        self.assertEqual(self.present.email, "present@example.org")

    def test_local_accounts_are_never_touched(self):
        deactivate_departed_users(self.exists)
        self.local_admin.refresh_from_db()
        self.assertTrue(self.local_admin.is_active)
        self.assertEqual(self.local_admin.email, "admin@example.org")

    def test_dry_run_changes_nothing(self):
        result = deactivate_departed_users(self.exists, dry_run=True)
        self.assertEqual(result.departed, ["gone"])
        self.gone.refresh_from_db()
        self.assertTrue(self.gone.is_active)

    def test_ldap_error_aborts_without_changes(self):
        def broken(username):
            raise LdapUnavailable("server down")

        with self.assertRaises(LdapUnavailable):
            deactivate_departed_users(broken)
        self.assertEqual(User.objects.filter(is_active=False).count(), 0)

    def test_mass_deactivation_needs_force(self):
        for i in range(4):
            _ldap_user(f"student{i}")
        with self.assertRaises(SafetyStop):
            deactivate_departed_users(self.exists)
        self.assertEqual(User.objects.filter(is_active=False).count(), 0)

        result = deactivate_departed_users(self.exists, force=True)
        self.assertEqual(len(result.departed), 5)

    @override_settings(AUTH_LDAP_SERVER_URI="")
    def test_command_without_ldap_does_nothing(self):
        out = StringIO()
        call_command("deactivate_departed_ldap_users", stdout=out)
        self.assertIn("not configured", out.getvalue())
        self.gone.refresh_from_db()
        self.assertTrue(self.gone.is_active)


class LdapLookupTests(TestCase):
    """The real lookup must tell 'not found' apart from errors (python-ldap is faked here)."""

    def _fake_ldap(self):
        import types

        ldap = types.ModuleType("ldap")

        class LDAPError(Exception):
            pass

        ldap.LDAPError = LDAPError
        ldap_filter = types.ModuleType("ldap.filter")
        ldap_filter.escape_filter_chars = lambda value: value.replace("*", r"\2a")
        ldap.filter = ldap_filter
        return ldap, ldap_filter

    def test_found_missing_referral_and_error(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from accounts.departed import ldap_entry_lookup

        ldap, ldap_filter = self._fake_ldap()
        conn = MagicMock()

        def search_s(base, scope, filterstr, attrs):
            if "boom" in filterstr:
                raise ldap.LDAPError("server down")
            if "present" in filterstr:
                return [("uid=present,ou=People,dc=example,dc=org", {})]
            return [(None, ["ldap://referral.example.org"])]

        conn.search_s.side_effect = search_s
        search = SimpleNamespace(base_dn="ou=People,dc=example,dc=org", scope=2, filterstr="(uid=%(user)s)")
        with patch.dict(sys.modules, {"ldap": ldap, "ldap.filter": ldap_filter}), \
                patch("accounts.ldap_setup.bind_ldap_connection", return_value=conn), \
                override_settings(AUTH_LDAP_SERVER_URI="ldaps://ldap.example.org", AUTH_LDAP_USER_SEARCH=search):
            with ldap_entry_lookup() as exists:
                self.assertTrue(exists("present"))
                self.assertFalse(exists("gone"))
                with self.assertRaises(LdapUnavailable):
                    exists("boom")
            self.assertEqual(conn.search_s.call_args_list[0].args[2], "(uid=present)")

            # Bind failure: nothing can be checked.
            with patch("accounts.ldap_setup.bind_ldap_connection", return_value=None):
                with self.assertRaises(LdapUnavailable):
                    with ldap_entry_lookup():
                        pass
        conn.unbind_s.assert_called_once()
