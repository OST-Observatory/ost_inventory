# Projektplan: Inventarsystem Sternwarte

> **Zweck dieses Dokuments:** Verbindlicher Entwicklungsplan für ein webbasiertes
> Inventarsystem. Dient als Referenz und Kontext für die Entwicklung (Cursor/AI-Agent).
> Bei Implementierungsentscheidungen gilt: Einfachheit und Wartbarkeit vor Features.
> Offene Alternativen sind geschlossen — dieses Dokument ist die Bauanleitung.

---

## 1. Zielbild

Webbasiertes Inventarsystem für ein Astronomie-Institut mit kleiner Sternwarte.

- **Umfang:** > 1.000 Inventarpositionen
- **Nutzer:** ~5 aktiv Pflegende, ~15–20 Lesende
- **Erfolgskriterium:** Das System wird nur genutzt, wenn es *radikal einfach* ist.
  Vielbeschäftigte Nutzer müssen in Sekunden suchen, finden und ändern können.
  Jede UI-Entscheidung ist diesem Ziel unterzuordnen.

### Kernanforderungen

- Items mit: Name, Beschreibung, Anzahl, Ort (beliebige Hierarchietiefe), Kommentar,
  Foto (Upload + direkte Kamera-Aufnahme mobil), bis zu 3 Kategorien, optionaler Typ
  (freie Bezeichnung mit Autocomplete aus bestehenden Typen, z. B. „Schmalbandfilter“ —
  **nicht** an eine Kategorie gebunden)
- Inventarnummer = Primary Key, Anzeige als `#0001` (zero-padded); kein separates Präfix-Feld
- Automatische Erfassung: wann angelegt/geändert, von wem
- Ausleihe: Ausleiher (auch **Externe**, keine System-Accounts!), Kontakt,
  geplanter Rückgabetermin; Rücknahme; vollständige Historie pro Item
- Übersicht aller aktuell ausgeliehenen Positionen, überfällige hervorgehoben
- E-Mail-Erinnerung bei überschrittenem Rückgabetermin
- CSV-Import und -Export
- QR-Code-Etiketten für Items und Orte (QR + Name + `#id`)
- Login via bestehendem **LDAP**, Rechte über dieselben Rollengruppen wie OSTdata
  (`student` / `supervisor` / `staff`)
- Mobile-first: Nutzung am Handy vor Ort in der Sternwarte

### Nicht-Ziele (bewusst ausgeschlossen — nicht implementieren!)

- Bestellwesen, Beschaffung, Preise, Abschreibung/Buchhaltung
- Reservierungen in der Zukunft (nur aktuelle Ausleihe)
- Mehrmandantenfähigkeit
- Mehrsprachige UI (nur Englisch)
- Nutzerverwaltung in der App (Rollen kommen aus LDAP)
- SPA / separates JS-Frontend-Framework
- Eigene LDAP-Gruppen `inventar-*` (werden nicht eingeführt)

---

## 2. Architektur & Stack

| Komponente   | Wahl                                            | Begründung                              |
|--------------|-------------------------------------------------|------------------------------------------|
| Backend      | Django 5.x (LTS)                                | Vorhandenes Betriebswissen im Institut    |
| Datenbank    | PostgreSQL                                      | Vorhanden; Volltextsuche + pg_trgm        |
| Frontend     | Django-Templates + htmx + **Pico.css** (CDN)    | Kein JS-Build-System; Pico statt Bootstrap |
| Auth         | `django-auth-ldap` (Pattern wie OSTdata)        | Bestehender LDAP-Server                   |
| Fotos        | Media-Storage (Dateisystem) + `easy-thumbnails` | DB bleibt schlank                         |
| CSV          | `django-import-export` + Management-Command     | Generisch + einmaliger Erstimport         |
| QR-Codes     | `segno`                                         | Reine Python-Lib, keine Systemabhängigkeiten |
| Erinnerungen | Management-Command + systemd-Timer/Cron         | Kein Celery/Redis nötig                   |
| Deployment   | **gunicorn + systemd + Apache**                 | Wie bestehende OST-Apps (nicht nginx)     |
| Deps         | `requirements.txt` + venv                       | Wie Weather/OSTdata; kein Node im Betrieb |

**Referenzprojekte:**

- Scaffold / Settings / Deploy: `ost_weather_station_website`
  (Settings-Split, `django-environ`, Gunicorn-Socket, systemd, Apache)
- LDAP: `ost_data_archive` → `OSTdata/users/ldap_setup.py`
  (env-gesteuert, `GroupOfNamesType`, `memberUid`-Fallback, ModelBackend-Fallback)

**Grundprinzipien:**

- Server-seitiges Rendering; htmx nur für: Live-Suche/Filter, abhängige
  Location-Auswahl, Type-Autocomplete, Ausleihe-Dialog, „Still here“-Button.
- Keine zusätzlichen Dienste (kein Redis, kein Celery, kein Node im Betrieb).
- Konfiguration über Umgebungsvariablen (`.env`), Secrets nie im Repo.
- Wenn `LDAP_SERVER_URI` leer: nur `ModelBackend` (lokale Dev / Notfall).

### 2.1 Repo-Struktur (verbindlich)

```
ost_inventory/
  manage.py
  requirements.txt
  .env.example
  config/                     # Django project package
    settings.py               # gemeinsame Basis
    settings_development.py
    settings_production.py
    urls.py
    wsgi.py
  inventory/                  # Domain-App
    models.py
    views/
    forms.py
    urls.py
    admin.py
    templatetags/
    management/commands/
  accounts/                   # Custom User, LDAP-Helfer, Mixins, permissions
  templates/
  static/
  deploy/
    apache/
    systemd/
  tests/
```

**Stabile Kurz-URLs (unveränderlicher Vertrag für gedruckte Etiketten):**

- Item: `/i/<id>/`
- Location: `/l/<id>/`
- IDs werden nie recycelt (Soft-Delete statt Hard-Delete für normale Nutzer).

Unter Subpath-Deployment ggf. `FORCE_SCRIPT_NAME` setzen (wie Weather).

---

## 3. Datenmodell

```python
# Skizze — Feldnamen verbindlich

class User(AbstractUser):
    # Custom User von Anfang an (OSTdata-Vorbild)
    is_supervisor = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    # is_staff / is_superuser kommen von AbstractUser

class Location(models.Model):
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.PROTECT, related_name="children",
    )
    # Beliebige Hierarchietiefe — keine Max-Tiefe-2-Validation.
    # Hilfsmethode path_display() → "Sternwarte / Schrank A / Kiste 3"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

class ItemType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # Kein category-FK. Name case-insensitive normalisiert speichern
    # (z. B. strip + konsistente Kleinschreibung für Uniqueness-Check,
    #  Anzeige mit Original-Schreibweise des ersten Eintrags).

class Item(models.Model):
    name = models.CharField(max_length=200)               # Pflicht
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    item_type = models.ForeignKey(
        ItemType, null=True, blank=True, on_delete=models.SET_NULL,
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT)  # Pflicht
    comment = models.TextField(blank=True)
    photo = models.ImageField(upload_to="items/%Y/%m/", null=True, blank=True)
    categories = models.ManyToManyField(Category, blank=True)
    # Validierung in clean(): max. 3 Kategorien; keine Typ↔Kategorie-Kopplung
    is_active = models.BooleanField(default=True)         # Soft-Delete
    last_seen_at = models.DateTimeField(null=True, blank=True)  # Mini-Inventur
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="items_created",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="items_updated",
    )

    @property
    def inventory_number(self) -> str:
        return f"#{self.pk:04d}"

class Loan(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="loans")
    borrower_name = models.CharField(max_length=200)      # Freitext — auch Externe!
    borrower_contact = models.CharField(max_length=200, blank=True)  # Mail/Telefon
    borrowed_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    # ↑ schon im MVP-Modell, nicht erst Phase 3

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=Q(returned_at__isnull=True),
                name="one_open_loan_per_item",
            ),
        ]
```

**Abgeleitete Logik:**

- `Item.current_loan` → Loan mit `returned_at IS NULL` (max. 1, per Constraint)
- `Item.is_lent` → bool
- Ausleihhistorie = alle Loans eines Items, chronologisch
- Ein Item = ein ausleihbares Objekt. Mengenartikel (Kabel etc.) haben nur
  `quantity` als Bestand, keine Teilmengen-Ausleihe.
- Soft-Delete: Schreibende setzen `is_active=False`; Hard-Delete nur Admin (`staff`)

**ItemType-UI (verbindlich):**

- Optionales Textfeld „Type“
- Während der Eingabe Vorschläge aus bestehenden `ItemType.name`
  (Präfix-/Substring-Match via htmx oder `<datalist>`)
- Neuer Name → `get_or_create`; bekannter Name → bestehender Typ
- Filterchip „Type“ auf der Startseite nutzt die Typ-Katalogliste

**Location-UI (verbindlich):**

- Beliebige Tiefe; Anzeige als Breadcrumb/Pfad
- Abhängige Auswahl per htmx (Kinder des gewählten Knotens laden)
- QR `/l/<id>/` zeigt Items an diesem Ort und optional in Unterorten

**Indizes:**

- `SearchVectorField` (GIN) über `name`, `description`, `comment` und Typ-Name
- `pg_trgm`-Extension für Tippfehlertoleranz (`CREATE EXTENSION pg_trgm`)
- B-Tree auf `Loan.due_date`, `Item.location`

### 3.1 CSV-Importschema (Phase 1 — fest)

Der Erstimport erwartet CSV mit diesen Spalten (Header-Namen verbindlich).
ODS wird vor dem Import nach CSV konvertiert; Spalten-Mapping der Bestands-.ods
passiert bei Vorliegen der Datei und blockiert den Import-Code nicht.

| Spalte            | Pflicht | Hinweis                                      |
|-------------------|--------|----------------------------------------------|
| `name`            | ja     | Item-Name                                    |
| `location_path`   | ja     | z. B. `Sternwarte/Schrank A/Kiste 3`         |
| `description`     | nein   |                                              |
| `quantity`        | nein   | Default 1                                    |
| `categories`      | nein   | Semikolon-getrennt, max. 3                   |
| `item_type`       | nein   | Freier String → get_or_create                |
| `comment`         | nein   |                                              |

Command: `import_inventory --file=… [--dry-run]`; legt fehlende Locations/Categories/Types an;
wiederholbar mit Fehlerbericht.

---

## 4. LDAP & Rechtemodell

**Prinzip:** Authentifizierung und Rollen kommen aus LDAP — dieselben Gruppen wie OSTdata.
Keine Nutzerpflege in Django. Externe Ausleiher sind reine Datensätze, keine Accounts.
Keine eigenen `inventar-read` / `inventar-write` / `inventar-admin` Gruppen.

### Rollen-Mapping (OSTdata → Inventar)

| OSTdata-Rolle | Env-Variable                 | Inventar-Rechte |
|---------------|------------------------------|-----------------|
| `student`     | `LDAP_GROUP_STUDENT_DN`      | Lesen: suchen, ansehen, CSV-Export |
| `supervisor`  | `LDAP_GROUP_SUPERVISOR_DN`   | + Schreiben: anlegen/bearbeiten, Ausleihe/Rücknahme, Fotos, CSV-Import, „Still here“ |
| `staff`       | `LDAP_GROUP_STAFF_DN`        | + Admin: Django-Admin, Items hard-löschen/reaktivieren, Stammdaten pflegen |
| Superuser     | `LDAP_GROUP_SUPERUSER_DN`    | Bypass / Notfall (`is_superuser`) |

Rechte-Helfer:

- `user_can_read(user)` — `is_student` **oder** `is_supervisor` **oder** `is_staff` (oder superuser)
- `user_can_write(user)` — `is_supervisor` **oder** `is_staff` (oder superuser)
- `user_can_admin(user)` — `is_staff` (oder superuser)

### Konfiguration (OSTdata-Pattern)

```python
# accounts/ldap_setup.py — analog OSTdata/users/ldap_setup.py
# Wird aus settings aufgerufen, wenn LDAP_SERVER_URI gesetzt ist.

AUTH_LDAP_SERVER_URI = env.str("LDAP_SERVER_URI", default="")
AUTH_LDAP_START_TLS = env.bool("LDAP_START_TLS", default=False)
AUTH_LDAP_BIND_DN = env.str("LDAP_BIND_DN", default="")
AUTH_LDAP_BIND_PASSWORD = env.str("LDAP_BIND_PASSWORD", default="")
AUTH_LDAP_USER_SEARCH_BASE = env.str("LDAP_USER_SEARCH_BASE", default="")
AUTH_LDAP_GROUP_SEARCH_BASE = env.str("LDAP_GROUP_SEARCH_BASE", default="")
AUTH_LDAP_USER_FILTER = env.str("LDAP_USER_FILTER", default="(uid=%(user)s)")
AUTH_LDAP_CONNECT_TIMEOUT = env.int("LDAP_CONNECT_TIMEOUT", default=5)

LDAP_GROUP_STAFF_DN = env.str("LDAP_GROUP_STAFF_DN", default="")
LDAP_GROUP_SUPERUSER_DN = env.str("LDAP_GROUP_SUPERUSER_DN", default="")
LDAP_GROUP_SUPERVISOR_DN = env.str("LDAP_GROUP_SUPERVISOR_DN", default="")
LDAP_GROUP_STUDENT_DN = env.str("LDAP_GROUP_STUDENT_DN", default="")

# Default: GroupOfNamesType; memberUid-Fallback wie OSTdata
# AUTH_LDAP_REQUIRE_GROUP = student | supervisor | staff
# Flags: is_staff, is_superuser, is_supervisor, is_student
# Nach Login Django-Gruppen staff / supervisor / student spiegeln

AUTHENTICATION_BACKENDS = [
    "django_auth_ldap.backend.LDAPBackend",   # nur wenn URI gesetzt
    "django.contrib.auth.backends.ModelBackend",
]

SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 h — Rechteentzug wirkt beim nächsten Login
```

### Durchsetzung im Code

- `WriteRequiredMixin` / `@write_required` und `AdminRequiredMixin` / `@admin_required`
  für **alle** schreibenden bzw. Admin-Views — Rechte immer backendseitig;
  UI blendet Buttons nur zusätzlich aus
- Schreibende deaktivieren Items (`is_active=False`); Hard-Delete nur Admin
- Lokaler Notfall-Superuser (ModelBackend), Passwort im Instituts-Passwort-Safe
- Phase 0 ohne LDAP: lokal testbar über ModelBackend + gesetzte Flags/Gruppen

---

## 5. UI-Prinzipien (Erfolgsfaktor!)

1. **Startseite = Suchfeld.** Volltextsuche über Name, Beschreibung, Kommentar, Typ.
   Darunter Filterchips: Kategorie, Ort, Typ, „nur ausgeliehene“. Keine
   Dashboard-Kacheln, keine Statistiken.
2. **Maximal 2 Klicks zu jeder Aktion.** Suchen → Item → „Loan“.
   Ausleihe-Dialog: 3 Felder (Name, Kontakt, Rückgabedatum), fertig.
3. **Item anlegen auf einer Seite.** Pflichtfelder nur Name + Ort. Alles andere
   optional — lieber ein unvollständiger Eintrag als gar keiner.
   Type = freies Autocomplete-Feld; Location = hierarchische Auswahl.
4. **Mobile-first.** Foto-Upload mit `<input type="file" accept="image/*"
   capture="environment">` öffnet direkt die Kamera. Alle Kernflows am
   echten Handy testen.
5. **Stabile Kurz-URLs** für QR-Codes: `/i/<id>/`, `/l/<id>/`.
6. **Rücknahme = ein Klick.** „Still here“-Bestätigung = ein Klick.
7. **UI-Sprache:** Englisch.

---

## 6. Phasenplan

### Phase 0 — Fundament (2–3 Tage)

- [ ] Projekt-Setup analog Weather: Repo, Settings-Split, `.env.example`,
      `requirements.txt`, Custom User Model
- [ ] LDAP-Config verdrahten (OSTdata-Pattern); ohne URI nur ModelBackend —
      lokal mit Flags/Gruppen testbar
- [ ] Datenmodell + Migrations (inkl. `pg_trgm`, UniqueConstraint offene Ausleihe,
      `last_reminder_sent_at`)
- [ ] Django-Admin-Registrierung (Location, Category, ItemType, Item, Loan)
- [ ] Rechte-Helfer `user_can_read/write/admin` + Mixins + Tests
- [ ] Lokaler Notfall-Superuser

**Meilenstein M0:** App startet lokal; Rechte-Tests grün ohne LDAP.
LDAP-Smoke-Test (Login + Rollenflags) sobald DNs in `.env` stehen — separat.

### Phase 1 — MVP (2 Wochen)

- [ ] **Suche/Startseite:** Postgres-Volltextsuche (`SearchVector` + `pg_trgm`),
      Filterchips, Ergebnisliste mit Thumbnail, Ort-Pfad, Ausleihstatus-Badge,
      Inventarnummer `#id`; htmx für Live-Filterung; Pagination
- [ ] **Item-Detailseite:** alle Felder, Foto groß, Ausleihhistorie,
      Aktions-Buttons je nach Rechten
- [ ] **Item anlegen/bearbeiten:** eine Seite; Pflicht nur Name + Ort;
      Kamera-Upload; Location-Auswahl beliebig tief (htmx);
      Type-Autocomplete (frei + Vorschläge); max. 3 Kategorien
- [ ] **Ausleihe:** Dialog (Name, Kontakt, Rückgabedatum); Rücknahme per
      Ein-Klick; Constraint: max. 1 offene Ausleihe pro Item
- [ ] **Übersicht „Currently on loan“:** sortiert nach Fälligkeit,
      überfällige hervorgehoben
- [ ] **Erstimport:** Management-Command für festes CSV-Schema (Abschnitt 3.1);
      `--dry-run` mit Fehlerbericht
- [ ] Responsive Layout (Pico.css), Kernflows am echten Handy getestet
- [ ] Deployment auf Zielserver (gunicorn + systemd + Apache, Media-Verzeichnis,
      Backups; ggf. `FORCE_SCRIPT_NAME`)

**Meilenstein M1:** System live, Bestandsdaten importiert, 2–3 Pilotnutzer
arbeiten produktiv damit.

### Phase 2 — Pilotbetrieb & Feedback (2 Wochen Kalenderzeit, ~2–3 Tage Arbeit)

- [ ] Alle Nutzer einladen; Kurzeinführung (15 min — wenn mehr nötig ist,
      ist das UI-Ziel verfehlt)
- [ ] Feedback sammeln, kleine UX-Korrekturen sofort umsetzen
- [ ] Beobachten: Wird gepflegt? Wo hakt es?
      → **Feedback steuert Priorisierung von Phase 3**

**Meilenstein M2:** Go-/Anpassungsentscheidung für den Ausbau.

### Phase 3 — Ausbau (1,5–2 Wochen)

- [ ] **QR-Etiketten:** Generator-View — Auswahl mehrerer Items/Orte →
      druckbare Bögen (Print-CSS, generisches Avery-ähnliches Raster als Default);
      QR → `/i/<id>/` bzw. `/l/<id>/`; Etikett: QR + Name + `#id`
- [ ] **Mail-Erinnerungen:** Command `send_overdue_reminders`, täglich per
      systemd-Timer; SMTP über `EMAIL_*` env; Mail an `recorded_by` und — falls
      `borrower_contact` eine Mailadresse ist — an den Ausleiher;
      Mehrfachversand-Schutz via `last_reminder_sent_at`
- [ ] **CSV generisch:** Export der aktuellen Suchtreffer und des Gesamtbestands;
      Import via `django-import-export` mit Preview und Zeilen-Fehlerbericht
- [ ] **Mini-Inventur:** „Still here ✓“-Button (`last_seen_at`);
      Übersicht „not confirmed recently“
- [ ] **Ausleihhistorie** verfeinern falls Pilot-Feedback es verlangt;
      Übersicht aller vergangenen Ausleihen mit Suche
- [ ] UX-Feinschliff aus Phase-2-Feedback

**Meilenstein M3:** Voller Funktionsumfang live.

### Phase 4 — Betrieb (laufend)

- [ ] Dokumentation: kurzes Betriebs-README (Deployment, Backup/Restore,
      LDAP-Rollen wie OSTdata, Cron-Jobs, Notfall-Admin)
- [ ] Backup: täglicher `pg_dump` + Media-Verzeichnis (rsync/borg),
      Restore einmal testen
- [ ] Dependency-Updates quartalsweise; Django-LTS-Upgrades geplant
- [ ] Jährliche Mini-Inventur-Runde mit QR-Scan etablieren

---

## 7. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| System wird nicht gepflegt → Datenstand veraltet | Radikal einfaches UI, QR-Codes, Mini-Inventur, Pflichtfelder minimal |
| LDAP-Schema weicht von Annahmen ab | OSTdata-Pattern + env-Vars; memberUid-Fallback; lokal ohne LDAP entwickelbar |
| LDAP nicht erreichbar | Lokaler Notfall-Superuser, ModelBackend als Fallback |
| Erstimport mit schmutzigen Daten | Dry-Run-Modus, Fehlerbericht, Import wiederholbar |
| Gedruckte QR-Etiketten werden ungültig | URLs `/i/<id>/` als stabiler Vertrag, IDs nie recyceln |
| Bus-Faktor (eine Wartungsperson) | Standard-Stack, wenig Abhängigkeiten, Betriebs-README |

---

## 8. Definition of Done

### Phase 0

- App lokal startfähig (Postgres oder Dev-DB laut Settings)
- Rechte-Helfer + Mixins getestet ohne LDAP
- Datenmodell migriert inkl. Constraints und `pg_trgm`

### LDAP (sobald DNs gesetzt)

- Login per LDAP; Flags `is_student` / `is_supervisor` / `is_staff` / `is_superuser`
  wie bei OSTdata

### Gesamt

- Alle Kernanforderungen aus Abschnitt 1 umgesetzt und mobil getestet
- Schreibrechte in allen Views backendseitig durchgesetzt (Tests vorhanden)
- Bestandsdaten vollständig importiert
- Backup + Restore einmal erfolgreich durchgespielt
- Betriebs-README vorhanden
- Ein Nutzer ohne Einweisung findet ein Item und trägt eine Ausleihe ein,
  ohne nachzufragen (informeller Usability-Test mit 1–2 Kollegen)

---

## 9. Defaults vs. Go-Live-Klärung

### Defaults (jetzt gültig — Code darauf aufbauen)

| Thema | Festlegung |
|-------|------------|
| CSS | Pico.css (CDN) |
| Deploy | Gunicorn + systemd + Apache |
| Inventarnummer | PK, Anzeige `#0001` |
| Location | Beliebige Hierarchietiefe |
| ItemType | Frei + Autocomplete, nicht kategoriegebunden |
| LDAP-Rollen | OSTdata: `student` / `supervisor` / `staff` |
| LDAP-Schema-Default | `groupOfNames` + Login per `uid`; memberUid-Fallback |
| Etiketten | Generisches Print-CSS (Avery-ähnlich) |
| UI-Sprache | Englisch |

### Vor Go-Live klären (blockiert **nicht** den Code)

- [ ] LDAP-DNs in `.env` setzen (Gruppen existieren institutsintern bereits)
- [ ] Spaltenstruktur der bestehenden .ods-Liste sichten → Mapping auf CSV-Schema 3.1
- [ ] SMTP (`EMAIL_*`) für Mail-Erinnerungen
- [ ] Konkreter Etikettenbogen/Drucker falls vom Default abweichen
