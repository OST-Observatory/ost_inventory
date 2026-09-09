# OST Inventory

Web-based inventory system for the observatory / astronomy institute.

See [`ost_inventory_initial.plan.md`](ost_inventory_initial.plan.md) for the full specification.

## Quick start (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
python manage.py migrate
python manage.py createsuperuser   # set is_supervisor or is_staff as needed
python manage.py runserver
```

Local auth uses Django’s `ModelBackend` when `LDAP_SERVER_URI` is empty.

Role flags on the user still map onto Django groups at login (`student`, `supervisor`, `staff`).
What those groups may do is configured under **Admin → Access control**:

| Default group | Rights |
|------|--------|
| `student` | Read (no borrower PII, no inactive items) |
| `supervisor` | Read + write, borrower PII, inactive items, labels, CSV import |
| `staff` | Supervisor rights + permanent delete + access control |
| Superuser | All permissions (bypass) |

`is_staff` still controls the Django admin site. Extra local groups can be created under **Admin → Groups**.

## LDAP

Configure the same env vars as OSTdata (`LDAP_SERVER_URI`, group DNs, …) in `.env`.
When the URI is set, `accounts/ldap_setup.py` enables `django-auth-ldap` and syncs
`is_student` / `is_supervisor` / `is_staff` / `is_superuser`.

Production requires `ldaps://` or `LDAP_START_TLS=True`. A STARTTLS failure does
not fall back to plaintext bind.

## Useful commands

```bash
# CSV import (dry-run first; dry-run does not write)
python manage.py import_inventory --file=data.csv --dry-run
python manage.py import_inventory --file=data.csv

# Overdue loan emails (systemd timer in deploy/)
# Dry-run logs loan IDs and recipient counts, not addresses.
python manage.py send_overdue_reminders --dry-run
python manage.py send_overdue_reminders

python manage.py test
```

CSV columns: `name`, `location_path` (required; `PRA/2a` = room/place); optional `description`, `quantity`,
`quantity_approximate` (`yes`/`true`/`1`), `container`, `categories` (semicolon-separated, max 4;
legacy `item_type` is merged into categories), `project`, `comment`.
Limits: 2 MB, 2000 rows, 500 characters/field, location depth 2.

## Stable QR URLs

- Item: `/i/<id>/`
- Location: `/l/<id>/`

Do not change these paths.

## Production deploy

1. Install under e.g. `/opt/ost_inventory`, create venv.
2. Install locked dependencies: `pip install --require-hashes -r requirements.lock`
   (do not install production from unconstrained `requirements.txt`).
3. Copy `.env.example` to a file **owned by the service user** (not world-readable):
   `install -m 600 .env.example /opt/ost_inventory/.env` then fill secrets.
   Set `DJANGO_ENV=production`, Postgres, LDAP, `ALLOWED_HOSTS`, `TRUSTED_ORIGIN`, `EMAIL_*`.
   The systemd unit also forces `DJANGO_ENV=production`.
4. `python manage.py migrate && python manage.py collectstatic`
5. Install units from `deploy/systemd/` and Apache snippet from `deploy/apache/`
   (HTTPS redirect, `X-Forwarded-Proto`, no public media alias).
6. If served under a subpath, set `FORCE_SCRIPT_NAME=/inventory` (or similar)

Regenerate the lockfile after bumping `requirements.txt`:

```bash
pip install pip-tools
pip-compile --generate-hashes -o requirements.lock requirements.txt
```

### Backup

- Daily `pg_dump` of the database
- Media directory (`MEDIA_ROOT`) via rsync/borg
- Test restore at least once

## Tests

```bash
python manage.py test tests
```

## Security and operations

### Implemented defaults

- Production refuses unknown `DJANGO_ENV`, debug mode, placeholder `SECRET_KEY`, empty
  `ALLOWED_HOSTS`, and non-Postgres databases.
- HTTPS redirect and HSTS are on in production; cookies are Secure.
- LDAP in production is TLS-only; STARTTLS errors abort without binding.
- Photos are served only after login/role checks; uploads are re-encoded, size-capped,
  and stored under UUID names.
- CSV dry-run is rolled back; import/export size and formula injection are limited.
- Login is rate-limited in-app (5 failures / 10 minutes, then 15-minute backoff).
- Pico CSS and htmx are self-hosted; CSP and Permissions-Policy headers are set.
- Borrower name/contact are visible only with the “See borrower name and contact” permission.
- Reminder dry-run does not print email addresses. Keep journal access restricted.

`.env` must be `chmod 600` and owned by the service user. The development `.env` in a
shared checkout is not a production secret store.

### Further recommendations

These are not implemented in this repository and should be handled operationally:

- Run the service as a dedicated Unix user instead of shared `www-data`.
- Firewall: only 80/443 from the campus network (or VPN); no direct Gunicorn/TCP.
- PostgreSQL: role without SUPERUSER/CREATEDB/CREATEROLE; separate migration credentials;
  `DATABASE_SSLMODE=verify-full` plus a CA when the database is remote.
- Backups: encrypt dumps, split encryption keys from the app host, keep an immutable
  or offsite copy, restrict who can restore, and test restores on a schedule.
- CI: secret scan, `manage.py check --deploy`, test suite, `pip-audit` / OSV against
  `requirements.lock`, and an SBOM per release.
- Data lifecycle: retention and anonymization for loans, photos, logs, and backups;
  a documented subject-access process.
- Prefer SSO/MFA; restrict the local emergency admin to a jump host or VPN.
- Pin installs to an internal package mirror when available.
- After a `SECRET_KEY` leak or rotation, existing sessions and signed tokens are invalid
  and users must sign in again.
- Optional extra login protection: Apache `mod_ratelimit` or Fail2ban on `/login/`.
