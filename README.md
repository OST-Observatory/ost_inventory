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
`quantity_approximate` (`yes`/`true`/`1`), `container`, `categories` (semicolon-separated, max 4), 
`project`, `comment`.
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
   Set `DJANGO_ENV=production`, PostgreSQL (see below), LDAP, `ALLOWED_HOSTS`, `TRUSTED_ORIGIN`, `EMAIL_*`.
   The systemd unit also forces `DJANGO_ENV=production`.
4. Create the database, then `python manage.py migrate && python manage.py collectstatic`
5. Install units from `deploy/systemd/` and Apache snippet from `deploy/apache/`
   (HTTPS redirect, `X-Forwarded-Proto`, no public media alias).
6. If served under a subpath, set `FORCE_SCRIPT_NAME=/inventory` (or similar)

Regenerate the lockfile after bumping `requirements.txt`:

```bash
pip install pip-tools
pip-compile --generate-hashes -o requirements.lock requirements.txt
```

### PostgreSQL

Production **requires** PostgreSQL (`DJANGO_ENV=production` refuses SQLite). Development
keeps using SQLite; do not copy `db.sqlite3` onto the server. Search uses Postgres
full-text search plus the `pg_trgm` extension (migration `inventory.0002_pg_trgm`).

Install the server and extension files (Debian/Ubuntu):

```bash
sudo apt install postgresql postgresql-contrib
```

Create a dedicated role **without** `SUPERUSER`, `CREATEDB`, or `CREATEROLE`, and a
UTF-8 database owned by that role so the first `migrate` can install `pg_trgm`
(it is a trusted extension; the database owner may `CREATE EXTENSION`):

```sql
-- as a PostgreSQL superuser (e.g. sudo -u postgres psql)
CREATE ROLE ost_inventory LOGIN PASSWORD 'use-a-long-random-password';
CREATE DATABASE ost_inventory
  OWNER ost_inventory
  ENCODING 'UTF8'
  LC_COLLATE 'C.UTF-8'
  LC_CTYPE 'C.UTF-8'
  TEMPLATE template0;
```

If `C.UTF-8` is missing, use another UTF-8 locale such as `en_US.UTF-8`. Confirm
with `\l` that encoding is `UTF8`.

Match `.env` to that database:

```
DJANGO_ENV=production
DATABASE_NAME=ost_inventory
DATABASE_USER=ost_inventory
DATABASE_PASSWORD=use-a-long-random-password
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_SSLMODE=prefer
```

Use `DATABASE_SSLMODE=verify-full` when the database is not on the app host (libpq
then checks the server certificate against the system CA, or `PGSSLROOTCERT`).
`prefer` is enough for a local socket or localhost with a server-side `hostssl`
rule. Restrict `pg_hba.conf` to `scram-sha-256` (and `hostssl` for remote clients).

On the app host, as the service user (`.env` is read from the project directory),
apply the existing migration chain (do not squash it for the first deploy) and
check the connection:

```bash
cd /opt/ost_inventory
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py migrate
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py check --deploy
```

`migrate` also seeds the default ACL groups (`student`, `supervisor`, `staff`).
Create an emergency local superuser if LDAP is not in place yet:
`python manage.py createsuperuser` (set `is_staff` / `is_supervisor` as needed).

Optional: a second database login with DML-only rights for gunicorn, while
`migrate` keeps using the database owner. After the first migrate, grant
`SELECT, INSERT, UPDATE, DELETE` on tables and `USAGE, SELECT` on sequences, plus
`ALTER DEFAULT PRIVILEGES` for future tables. The runtime user must not own the
database if you want this split to mean anything.

### Logging (journald)

The units write to the systemd journal (stderr, including gunicorn access/error).
There is no app log directory. Watch logs with:

```bash
journalctl -u ost-inventory -f
journalctl -u ost-inventory-reminders
journalctl -u ost-inventory -p warning
```

Restrict who can read the journal (reminder dry-run still omits addresses, but
request logs may contain paths). Do not grant `adm` / `systemd-journal` broadly.

### Email

Development prints mail to the console unless `EMAIL_HOST` or `EMAIL_METHOD` is
set. Production should use a real backend.

**Remote SMTP** (submission, STARTTLS):

```
EMAIL_METHOD=smtp
EMAIL_HOST=mail.example.edu
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=inventory
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=inventory@example.edu
```

**Local MTA** (Postfix/Exim on port 25) — this is the option that fits the
hardened units (`NoNewPrivileges=yes` cannot exec setgid `sendmail`):

```
EMAIL_METHOD=smtp
EMAIL_HOST=127.0.0.1
EMAIL_PORT=25
EMAIL_USE_TLS=False
EMAIL_USE_SSL=False
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=inventory@example.edu
```

Allow the service user to submit locally (Postfix `mynetworks` / `127.0.0.1`,
or a `smtpd` restriction that accepts the app host). Test with
`python manage.py send_overdue_reminders --dry-run` then a real run.

**sendmail binary** (`EMAIL_METHOD=sendmail`, default `EMAIL_SENDMAIL=/usr/sbin/sendmail`):
works if the binary is not setgid, or if you drop `NoNewPrivileges` on
`ost-inventory-reminders.service` only. Prefer SMTP to localhost instead.

`EMAIL_USE_TLS` and `EMAIL_USE_SSL` are mutually exclusive (587 + STARTTLS vs 465
+ implicit TLS).

### Backup

- Daily `pg_dump` of the database (encrypt the file; keep a copy off the app host):

```bash
sudo -u postgres pg_dump -Fc -d ost_inventory -f ost_inventory.dump
# restore onto an empty database owned by ost_inventory:
# sudo -u postgres pg_restore --clean --if-exists -d ost_inventory ost_inventory.dump
```

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
- App logs go to the systemd journal (no log directory on disk).
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
