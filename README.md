# OST Inventory

Web inventory for an observatory or astronomy institute: find equipment, record
where it lives, lend it out, print QR labels, and run a stocktake from a phone.

The interface is English. Everyone who uses the site must sign in. Photos are
never served as public files; they go through the app after a permission check.

## Features

- **Search** — name, description, comment, inventory number, location, project,
container, and host item. PostgreSQL adds full-text search and typo-tolerant
matching (`pg_trgm`). SQLite (development) uses case-insensitive contains.
- **Items** — room plus optional place (e.g. `PRA / 2a`), 1–4 categories,
optional project and container, quantity (exact or approximate), description,
comment, photo. **Installed in** links a part to a host item; the part then
follows the host’s location.
- **Photos** — upload on create/edit, or **Take photo** / **Replace photo** on
the item page (rear camera on a phone). JPEG, PNG, and WebP; max 5 MB; images
are re-encoded and stored under UUID names.
- **Loans** — one open loan per item, due date, optional borrower contact.
Borrower name and contact are hidden unless the user has that permission.
Overdue reminders can be sent daily.
- **Locations** — rooms and places, with a per-location item list.
- **QR labels** — PNG, ZIP, and ODS for T50-style sizes (50×80, 40×30, 40×20,
30×20 mm, plus a cable flag). Print from the label printer’s own app.
- **Stocktake** — a dated physical count (separate from **Still here** / not
seen recently).
- **CSV** — import (preview, then commit) and export. Matching on import is
active item + name + location.
- **Access control** — capabilities on Django groups, editable in the app
(**Admin → Access control**). Django’s `/admin/` is separate and follows
`is_staff`.

Stable QR targets (do not change these paths):


| Kind     | Path       |
| -------- | ---------- |
| Item     | `/i/<id>/` |
| Location | `/l/<id>/` |


The usual UI lives under `/inventory/` (search, item pages, tools). Short URLs
and `/login/` sit at the site root so a label still works if the app is moved
behind a hostname of its own.

## Requirements

- Python 3.12 (Django 5.2)
- Development: SQLite (created automatically)
- Production: PostgreSQL 14+, `postgresql-contrib` (`pg_trgm`)
- Label PNGs: DejaVu fonts (`fonts-dejavu-core` on Debian/Ubuntu)
- Production front: Apache with `ssl`, `headers`, `proxy`, `proxy_http`
- Optional: campus LDAP (`ldaps://` or LDAP + STARTTLS)

Do not copy `db.sqlite3` onto a production host. Production refuses SQLite,
debug mode, an empty `ALLOWED_HOSTS`, and a short or placeholder `SECRET_KEY`.

---



## Development

Use this on a laptop or a throwaway VM. It is not a production configuration.

### 1. Packages

Debian/Ubuntu:

```bash
sudo apt install python3 python3-venv python3-dev libpq-dev libldap2-dev libsasl2-dev \
  fonts-dejavu-core
```

`libpq-dev` and the LDAP libraries are needed to build `psycopg2` and
`python-ldap` from `requirements.txt`. Production installs wheels from the
lockfile and may skip the `-dev` packages if the wheels include them.

### 2. Checkout and virtualenv

```bash
git clone <repository-url> ost_inventory
cd ost_inventory
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```



### 3. Environment file

```bash
cp .env.example .env
chmod 600 .env
```

Keep `DJANGO_ENV=development`. You can leave `SECRET_KEY` as the example value
locally; production will reject it. Leave `LDAP_SERVER_URI` empty to use Django
username/password only. Mail goes to the console unless you set `EMAIL_HOST` or
`EMAIL_METHOD`.

### 4. Database and first user

```bash
python manage.py migrate
python manage.py createsuperuser
```

`migrate` creates SQLite at `db.sqlite3` and seeds groups `student`,
`supervisor`, and `staff` with the default capabilities below.

Open Django admin (`/admin/`) as that superuser and set **Supervisor** (and
usually **Staff**) on your user so you can add items. Superusers bypass the
capability checks; the flags still matter for everyone else.

```bash
python manage.py runserver
```

Sign in at [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/). Search is `/inventory/`.

### 5. Day-to-day

```bash
python manage.py test
python manage.py import_inventory --file=data/inventory_import.csv --dry-run
python manage.py import_inventory --file=data/inventory_import.csv
python manage.py send_overdue_reminders --dry-run
```

CSV files under `data/` are gitignored. Dry-run import rolls back; dry-run
reminders log loan IDs and recipient **counts**, not addresses.

To reset the local database: stop `runserver`, delete `db.sqlite3` (and
optionally `media/`), then `migrate` and `createsuperuser` again.

### Roles and capabilities

At login, `is_student` / `is_supervisor` / `is_staff` are mirrored onto the
Django groups of the same names. What those groups may do is stored as
capabilities (**Admin → Access control**), not hard-coded beyond the defaults:


| Group        | Default rights                                                   |
| ------------ | ---------------------------------------------------------------- |
| `student`    | Read (no borrower name/contact, no inactive items)               |
| `supervisor` | Read, write, borrower PII, inactive items, CSV import, QR labels |
| `staff`      | Supervisor rights, permanent delete, access-control UI           |
| Superuser    | All capabilities                                                 |


`is_staff` still gates `/admin/`. Extra groups can be created under
**Admin → Groups**.

### Optional LDAP in development

Set `LDAP_SERVER_URI` (and the search bases and group DNs) in `.env`. The
LDAP backend is added in front of `ModelBackend`. Group DNs map to
`is_student`, `is_supervisor`, `is_staff`, and `is_superuser`. Leave
`LDAP_TLS_CACERT` empty unless verification fails (see
[LDAP](#ldap) under production).

---



## Production

These steps assume Debian/Ubuntu, Apache, PostgreSQL on the same host, and
install path `/opt/ost_inventory`. Adjust hosts, users, and paths to match
the server. Use a dedicated Unix user instead of `www-data` if you can; the
shipped units use `www-data` so they work with a default Apache.

### 1. System packages

```bash
sudo apt install python3 python3-venv postgresql postgresql-contrib \
  apache2 libapache2-mod-ssl \
  fonts-dejavu-core
sudo a2enmod ssl headers proxy proxy_http
```

Need a compiler for LDAP/Postgres wheels only if pip cannot use binaries:

```bash
sudo apt install python3-dev libpq-dev libldap2-dev libsasl2-dev build-essential
```



### 2. Application user and directories

```bash
sudo mkdir -p /opt/ost_inventory /opt/ost_inventory/media /opt/ost_inventory/staticfiles
sudo chown -R www-data:www-data /opt/ost_inventory/media
sudo chmod 750 /opt/ost_inventory/media
```

Deploy the tree as a user who may write `/opt/ost_inventory` (git clone or
rsync), then make sure `www-data` can **read** the code and venv and **write**
`media/`.

### 3. Code and locked dependencies

```bash
cd /opt/ost_inventory
sudo python3 -m venv .venv
sudo /opt/ost_inventory/.venv/bin/pip install -U pip
sudo /opt/ost_inventory/.venv/bin/pip install --require-hashes -r requirements.lock
```

Do **not** install production from unconstrained `requirements.txt`. After
changing `requirements.txt` on a development machine:

```bash
pip install pip-tools
pip-compile --generate-hashes -o requirements.lock requirements.txt
```

Commit the new lockfile and install that on the server.

### 4. PostgreSQL

```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql
```

```sql
CREATE ROLE ost_inventory LOGIN PASSWORD 'use-a-long-random-password';
CREATE DATABASE ost_inventory
  OWNER ost_inventory
  ENCODING 'UTF8'
  LC_COLLATE 'C.UTF-8'
  LC_CTYPE 'C.UTF-8'
  TEMPLATE template0;
```

If `C.UTF-8` is missing, use another UTF-8 locale such as `en_US.UTF-8`.
Confirm encoding with `\l`. The role must **not** have `SUPERUSER`,
`CREATEDB`, or `CREATEROLE`. Owning the database is enough for `migrate` to
install the trusted `pg_trgm` extension.

Restrict `pg_hba.conf` to `scram-sha-256`. For a database on another host use
`hostssl` and `DATABASE_SSLMODE=verify-full` (libpq uses the system CA, or
`PGSSLROOTCERT`).

Optional: a second login that only has DML for gunicorn, while `migrate` keeps
using the owner. After the first migrate, grant `SELECT, INSERT, UPDATE, DELETE`
on tables, `USAGE, SELECT` on sequences, and `ALTER DEFAULT PRIVILEGES` for
future tables. That runtime user must not own the database.

### 5. Secrets (`.env`)

```bash
sudo install -m 600 -o www-data -g www-data .env.example /opt/ost_inventory/.env
sudo -u www-data editor /opt/ost_inventory/.env
```

Generate a secret (at least 50 characters; not the example string):

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Minimum production values:

```
DJANGO_ENV=production
SECRET_KEY=<output of the command above>
ALLOWED_HOSTS=inventory.example.edu
TRUSTED_ORIGIN=https://inventory.example.edu
FORCE_SCRIPT_NAME=
SECURE_SSL_REDIRECT=True
DATABASE_NAME=ost_inventory
DATABASE_USER=ost_inventory
DATABASE_PASSWORD=<database password>
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_SSLMODE=prefer
DEFAULT_FROM_EMAIL=inventory@example.edu
```

The systemd unit also sets `DJANGO_ENV=production`. `.env` must stay mode
`600` and owned by the service user. The development `.env` in a shared git
checkout is not a production secret store.

`TRUSTED_ORIGIN` is the CSRF origin (`https://` + host, no path). List several
hosts in `ALLOWED_HOSTS` as a comma-separated list if needed.

Leave `FORCE_SCRIPT_NAME` empty on a dedicated vhost (`ProxyPass /`). On a
shared host where the public URL is `https://host/inventory/…` and Apache
uses `ProxyPass /inventory`, set `FORCE_SCRIPT_NAME=/inventory` so links stay
`/inventory/labels/` instead of `/inventory/inventory/labels/`. Then alias
static files at `/inventory/static/` as well.

### 6. LDAP

Leave `LDAP_SERVER_URI` empty only if you will use local Django accounts
(emergency admin). Production LDAP must be `ldaps://` or `ldap://` with
`LDAP_START_TLS=True`. A STARTTLS failure does not fall back to a plaintext
bind.

Typical variables:

```
LDAP_SERVER_URI=ldaps://ldap.example.edu
LDAP_START_TLS=False
LDAP_BIND_DN=
LDAP_BIND_PASSWORD=
LDAP_USER_SEARCH_BASE=ou=people,dc=example,dc=edu
LDAP_GROUP_SEARCH_BASE=ou=groups,dc=example,dc=edu
LDAP_GROUP_STUDENT_DN=cn=inventory-students,ou=groups,dc=example,dc=edu
LDAP_GROUP_SUPERVISOR_DN=cn=inventory-supervisors,ou=groups,dc=example,dc=edu
LDAP_GROUP_STAFF_DN=cn=inventory-staff,ou=groups,dc=example,dc=edu
LDAP_GROUP_SUPERUSER_DN=
```

`LDAP_TLS_CACERT` is optional. Certificate checks are always on; an empty
value uses the system trust store (`/etc/ldap/ldap.conf` / `ca-certificates`).
Set it to a PEM file only if verification fails because the LDAP CA is not in
that store. Confirm with:

```bash
openssl s_client -connect ldap.example.edu:636 -showcerts </dev/null
# STARTTLS on 389:
openssl s_client -connect ldap.example.edu:389 -starttls ldap -showcerts </dev/null
```

`Verify return code: 0 (ok)` means you can leave `LDAP_TLS_CACERT` empty.

If login fails, do not turn on `DEBUG`. Probe from the app host:

```bash
cd /opt/ost_inventory
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py check_ldap
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py check_ldap --username YOUR_UID
journalctl -u ost-inventory -t ost-inventory -p info | grep -i ldap
```

Set `LDAP_DEBUG=True` temporarily for `django_auth_ldap` traces, then restart
and try one login. Typical causes: URI/STARTTLS mismatch, bind DN rejected,
wrong `LDAP_USER_SEARCH_BASE`, or the account not in any of the configured
role groups (`member` or `memberUid`). `LDAP_USER_FILTER` defaults to
`(uid=%(user)s)` and can stay empty.

### 7. Email

Development prints mail to the console. Production should send for real.

**Remote submission (STARTTLS):**

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

**Local MTA** (Postfix/Exim on port 25). This matches the hardened units:
`NoNewPrivileges=yes` cannot run a setgid `sendmail` binary.

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

Allow localhost in the MTA (`mynetworks` or an equivalent restriction).

`EMAIL_METHOD=sendmail` pipes to `EMAIL_SENDMAIL` (default `/usr/sbin/sendmail`).
Prefer SMTP to localhost unless that binary is not setgid.
`EMAIL_USE_TLS` and `EMAIL_USE_SSL` are mutually exclusive (587 vs 465).

### 8. Migrate, static files, deploy check

```bash
cd /opt/ost_inventory
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py migrate
sudo /opt/ost_inventory/.venv/bin/python manage.py collectstatic --noinput
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py check --deploy
```

Apply the existing migration chain; do not squash it for the first deploy.
`migrate` seeds the default ACL groups.

Create an emergency local superuser (especially before LDAP is proven):

```bash
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py createsuperuser
```

Set **Staff** / **Supervisor** in `/admin/` if that account should work in the
inventory UI as well as Django admin.

`collectstatic` may run as root; Apache only needs to read
`/opt/ost_inventory/staticfiles`.

### 9. systemd

```bash
sudo cp /opt/ost_inventory/deploy/systemd/ost-inventory.socket \
        /opt/ost_inventory/deploy/systemd/ost-inventory.service \
        /opt/ost_inventory/deploy/systemd/ost-inventory-reminders.service \
        /opt/ost_inventory/deploy/systemd/ost-inventory-reminders.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ost-inventory.socket ost-inventory.service
sudo systemctl enable --now ost-inventory-reminders.timer
sudo systemctl status ost-inventory.socket ost-inventory.service
```

Gunicorn listens on `unix:/run/ost-inventory/gunicorn.sock` (mode `0660`,
`www-data`). Logs go to the journal (no log directory):

```bash
journalctl -u ost-inventory -f
journalctl -u ost-inventory-reminders
journalctl -u ost-inventory -p warning
```

Restrict journal access (`adm` / `systemd-journal`). Reminder dry-run omits
addresses; access logs can still contain URL paths.

If you change `User=` in the units, also change socket ownership, `.env`
owner, `media/` owner, and Apache’s ability to connect to the socket.

Reminders run at 08:00 local time (`OnCalendar` in the timer). Test first:

```bash
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py send_overdue_reminders --dry-run
sudo systemctl start ost-inventory-reminders.service
```

### 10. Apache and TLS

Prefer a **dedicated vhost** so `/i/`, `/l/`, `/login/`, `/admin/`, `/media/`,
and `/inventory/` all hit gunicorn. Do **not** `Alias` `/media/`; photos are
served by Django after login.

The `|http://localhost/` part of `ProxyPass` is only the dummy URL Apache uses
with a Unix socket; it does not mean the app is bound to localhost. Forward the
site root so gunicorn sees the real paths:

```apache
RequestHeader set X-Forwarded-Proto "https"
RequestHeader unset X-Forwarded-For
LimitRequestBody 8388608

Alias /static /opt/ost_inventory/staticfiles
<Directory /opt/ost_inventory/staticfiles>
    Options -Indexes
    Require all granted
</Directory>

ProxyPass /static !
ProxyPass / unix:/run/ost-inventory/gunicorn.sock|http://localhost/
ProxyPassReverse / unix:/run/ost-inventory/gunicorn.sock|http://localhost/
```

A full example lives in `deploy/apache/ost-inventory.conf`. After changing
units or Apache, `daemon-reload` / restart the **socket and service**, then
`apache2ctl configtest` and reload Apache. Leave `FORCE_SCRIPT_NAME` empty.

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Firewall: 80/443 from campus or VPN only. Do not expose gunicorn’s socket or
a TCP bind on the network.

### 11. Smoke test

1. `https://inventory.example.edu/login/` (HTTP should redirect to HTTPS).
2. Sign in (LDAP or local superuser).
3. Open search, add a room under **Tools → Locations**, add an item, take or
  upload a photo, generate a QR PNG, scan `/i/<id>/`.
4. `journalctl -u ost-inventory -e` for errors.
5. Confirm static CSS loads (`/static/…`) and that a photo URL
  requires login.



### 12. Backups

- Daily encrypted `pg_dump` **off** the app host:

```bash
sudo -u postgres pg_dump -Fc -d ost_inventory -f ost_inventory.dump
# restore onto an empty database owned by ost_inventory:
# sudo -u postgres pg_restore --clean --if-exists -d ost_inventory ost_inventory.dump
```

- `media/` (item photos) via rsync or borg, same schedule.
- Test a restore on a spare database at least once.
- Split encryption keys from the app host; keep an immutable or offsite copy.



### 13. Updates

```bash
cd /opt/ost_inventory
sudo -u deploy git pull    # or rsync the release
sudo /opt/ost_inventory/.venv/bin/pip install --require-hashes -r requirements.lock
sudo -u www-data /opt/ost_inventory/.venv/bin/python manage.py migrate
sudo /opt/ost_inventory/.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart ost-inventory.service
```

---



## CSV format

Required: `name`, `location_path` (`Room` or `Room/Place`, e.g. `PRA/2a`).

Optional: `description`, `quantity`, `quantity_approximate` (`yes` / `true` /
`1`), `container`, `categories` (semicolon-separated, max 4), `project`,
`comment`, `installed_in` (inventory number such as `#0004` or numeric id; the
host must already exist).

Limits: 2 MB, 2000 rows, 500 characters per field, location depth 2. Formula-looking
cells are sanitised on export. Web import is under **Tools → Import**; the
management command is equivalent.

An active item with the same name at the same location is updated; otherwise a
row is created.

---



## Security (what the app already does)

- Production settings validation (Postgres, `SECRET_KEY`, `ALLOWED_HOSTS`, no debug).
- HTTPS redirect and HSTS; `Secure` cookies; `X-Forwarded-Proto` from Apache.
- CSP and Permissions-Policy; Pico CSS and htmx are self-hosted.
- LDAP in production is TLS-only.
- Login rate limit: 5 failures / 10 minutes, then 15 minutes backoff.
- Photos: authz, size/pixel cap, re-encode, UUID names, no public media alias.
- CSV dry-run is transactional; import/export size limits.
- Borrower PII only with the **See borrower name and contact** capability.

After a `SECRET_KEY` leak or rotation, sessions are invalid and everyone must
sign in again.

Operational (not implemented in this repo): dedicated service user, campus
firewall, `DATABASE_SSLMODE=verify-full` for remote Postgres, backup encryption
and restore drills, CI (`check --deploy`, tests, `pip-audit` on the lockfile),
data retention for loans/photos/logs, SSO/MFA, Fail2ban or `mod_ratelimit` on
`/login/`.