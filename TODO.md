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

**Status:** open. The central privacy policy
(`/static/datenschutz.html#en-inventory` on the landing site) promises limited
storage; the app does not enforce any retention yet.

- **Returned loans are kept forever**, including `borrower_name`,
  `borrower_contact` and `note` (`Loan` in `inventory/models.py`, ~295-336).
  Define a retention period (e.g. anonymise the borrower fields N months after
  `returned_at`, keep item, dates and `recorded_by` for the history) and add a
  management command plus a systemd timer next to `ost-inventory-reminders.timer`.
  Update the policy text with the chosen period.
- **Admin log contains borrower names.** `django_admin_log` stores
  `object_repr`, which is `Loan.__str__` (`"<item> → <borrower_name>"`), and is
  never pruned. The anonymisation command should also rewrite or delete old
  `LogEntry` rows for loans (or prune `LogEntry` in general after N months).
- **Expired sessions are never cleared.** Sessions expire after 12 h
  (`SESSION_COOKIE_AGE`) but stay in `django_session`. Schedule
  `manage.py clearsessions` (daily, same timer as above is fine).
- **Photos of deleted items stay on disk.** `item_delete` deletes the row but
  nothing removes the file under `media/items/` or its easy-thumbnails
  variants; there is no `post_delete` signal. The photo view (`item_photo`)
  deletes a replaced original but not its thumbnails — check the edit form's
  clear/replace path too. Add a `post_delete` handler (after commit, using
  `get_thumbnailer(...).delete(save=False)` or `delete_thumbnails()`) and a
  one-off cleanup for orphaned files.
- **Gunicorn access log contains query strings**, e.g.
  `GET /inventory/loans/history/?q=<borrower name>`, and goes to journald
  (`--access-logfile -` in `deploy/systemd/ost-inventory.service`). Either make
  sure journald keeps it no longer than the policy says (7 days,
  `MaxRetentionSec=7day` in `journald.conf` or a drop-in) or set
  `--access-logformat` without `%(q)s` / use `%(U)s` instead of `%(r)s`.
- **IPP print jobs carry the username.** `labels_print` passes
  `request.user.get_username()` as `requesting-user-name`
  (`inventory/views/extras.py`, `inventory/printing.py` ~261), so it ends up
  in the job history of the label-printer laptop. Consider a neutral value
  such as `"inventory"`.
- **Reminder failures may log addresses.** `send_overdue_reminders` logs
  failures with `logger.exception`; SMTP errors (e.g. `SMTPRecipientsRefused`)
  include the recipient addresses in the traceback. Log the exception class
  and loan id only, or accept that and cover it by the journald retention.
