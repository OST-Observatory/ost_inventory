# TODO

## Optional: label printing from more than one machine

**Status:** undecided. Direct printing works today with a single, server-wide
`LABEL_PRINTER_URI` pointing at the supvan-printer-app on one laptop
(`ipp://<host>:8631/ipp/print/<name>`). Colleagues who run supvan-cups on their
own machines cannot yet print from the web app to their own printer.

**Constraint that shapes every option:** the IPP job is sent by the Django
server, not by the browser. The server must reach the machine the printer is
plugged into (DNS name or IP, port 8631, firewall open). `.local` names only
resolve on the server with mDNS installed. Browser-to-localhost printing is not
an option: supvan-printer-app has no CORS support and the app's CSP forbids it.

### Option A: allow-list of a few standard laptops (leaning towards this)

- Admin configures several printers, e.g. `LABEL_PRINTERS=Lab laptop=ipp://…;Office=ipp://…`
  (or a small `LabelPrinter` model editable under Admin → Access control).
- Label preview and the item "Print label" dialog get a printer selector;
  the last choice is remembered in the session like size and code.
- Fits stationary or "house" laptops that keep a stable hostname.
- Work: settings parsing or model, selector partial, `labels_print` takes a
  printer key, `check_label_printer --printer <key>`, tests, README.

### Option B: per-user printer URI

- Each user stores their own URI in a profile page; `LABEL_PRINTER_URI` stays
  the default. Print goes to the URI of the logged-in user.
- Fits colleagues with their own laptop + printer, but every laptop must be
  reachable from the server and keep a resolvable name.
- Work: field on `accounts.User` or a `UserPreference` model + migration,
  profile page with "Test printer" button, `labels_print` reads the user's URI.

### Option C: no code change, print via the colleague's own CUPS

- supvan-printer-app is IPP Everywhere; the colleague's CUPS discovers it.
  Download the PNG from the preview and `lp -d <name> label.png`.
- Not one click; CUPS scaling is not pixel-exact.

### Applies to every option

- Each supvan-printer-app needs the same service drop-in as the reference
  install (`SUPVAN_MIRROR=1`, `SUPVAN_BLOCK_BUFFERS=0`, `RUST_LOG=info`),
  otherwise labels print mirrored or only the first ~40 mm.
- supvan-printer-app listens on all interfaces without authentication.
  Consider `SUPVAN_HOST=<LAN address>` and a firewall rule that admits only
  the Django server.
- Cable-flag labels: rotation direction and tab position still need a test on
  real 30 mm stock (`ROTATE_LANDSCAPE_DEGREES` in `inventory/printing.py`).
- Upstream: the two local supvan-cups patches (`SUPVAN_BLOCK_BUFFERS`,
  `SUPVAN_MIRROR`) are uncommitted in `~/projects/supvan-cups` and worth a
  pull request to heeen/supvan-cups.

## Optional: printing from Android

**Stage 1 — over the network, no development. Done (2026-09-21).** Android's
built-in print service discovers supvan-printer-app over mDNS as an IPP
Everywhere printer, so the T50 shows up in the Android print dialog while the
service runs on a machine in the same WLAN. The printer hangs on that machine,
not on the phone, and the print dialog scales a rendered page rather than
placing dots one-to-one. If the output is not sharp enough, a label-sized print
view (its own template plus `@page` rules at the label's mm size) would fix it
without touching the printer side.

**Stage 2 — own Android app, direct over Bluetooth. Undecided.**

Why the browser cannot do this itself, so nobody re-investigates: Web Bluetooth
speaks BLE/GATT only, while the T50M Pro is classic Bluetooth SPP (RFCOMM,
service UUID `00001101-0000-1000-8000-00805f9b34fb`, confirmed on our unit).
WebUSB refuses HID-class interfaces, and WebHID does not exist on Android. So
direct printing from the phone needs an installed app.

The cheapest shape that needs **no change to this web app**:

- Register the app as a **share target for `image/png`**. The existing Share
  button in the label preview already hands over the finished PNG
  (`bindSharePng` in `static/app.js`), which is exactly how the vendor's
  Katasymbol app is fed today.
- The app then does what supvan-printer-app does: PNG → 1 bit → mirror across
  the head → column-major repack → 4096-byte print buffers → LZMA → SPP
  transfer, plus a status poll. It reads the loaded label size from the
  printer's own RFID record (`RETURN_MAT`), so no size picker is needed.

Groundwork that already exists:

- `~/projects/supvan-cups/docs/PROTOCOL.md` — the reverse-engineered wire
  protocol, including frame layout, `PAGE_REG_BITS` and the LZMA parameters.
- `~/projects/supvan-cups/test_print.py` — a single-file, working reference of
  the whole Bluetooth print flow (~1100 lines of Python) to port.
- Our two hardware findings apply unchanged: send the page as **one** LZMA
  block (a sparse QR label compresses to under 1 KB) and **mirror** every
  printhead line, else the label prints right-to-left or breaks off after
  ~40 mm.

Notes for whoever builds it:

- Kotlin, `BluetoothSocket.createRfcommSocketToServiceRecord`, runtime
  permission `BLUETOOTH_CONNECT` (Android 12+); LZMA1 "alone" format via
  xz-java (`LZMAOutputStream`), dict 8192, lc=3, lp=0, pb=2, with the real
  uncompressed size patched into the header.
- A `PrintService` plugin (printer appears in every Android print dialog) is
  the nicer end state but much more work than the share target; the share
  target can come first.
- Rough estimate: a few days for someone with Android experience.
- Payoff over the status quo: independence from the vendor app and no manual
  step of inserting the image into its template. The vendor app keeps working
  either way.

## Data protection / retention

**Status:** done (2026-09). The central privacy policy
(`/static/datenschutz.html#en-inventory` on the landing site) states the retention;
README → *Data protection / retention* documents how it is enforced.

- [x] Returned loans anonymised 1 year after `returned_at` (`LOAN_RETENTION_DAYS=365`):
  borrower name, contact and note; item, dates and `recorded_by` stay —
  `manage.py purge_personal_data`, timer `ost-inventory-purge` (daily 03:30)
- [x] Admin log (`django_admin_log.object_repr`) of those loans rewritten by the same command
- [x] Expired sessions cleared by the same command
- [x] Photos + thumbnails removed after item delete / photo replace or clear
  (`inventory/signals.py`); leftovers once via `manage.py cleanup_orphan_photos`
- [x] Gunicorn access log with query strings: covered by journald retention (7 days)
- [x] IPP print jobs send `requesting-user-name` `inventory` instead of the username
- [x] Failed reminders log loan id + exception class only (no recipient addresses)
