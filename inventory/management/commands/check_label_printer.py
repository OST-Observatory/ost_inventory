from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Probe the IPP label printer (LABEL_PRINTER_URI) and optionally print a test label."

    def add_arguments(self, parser):
        parser.add_argument("--uri", default="", help="override LABEL_PRINTER_URI")
        parser.add_argument(
            "--test-page",
            action="store_true",
            help="send one test label to the printer",
        )
        parser.add_argument(
            "--size",
            default="40x30",
            help="label size key for --test-page (50x80, 40x30, 40x20, 30x20, cable-flag)",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        from inventory.printing import (
            PRINTER_STATES,
            PWG_RASTER_FORMAT,
            PrintError,
            ipp_get_printer_attributes,
            ipp_print_job,
            png_to_pwg_raster,
        )

        uri = options["uri"] or getattr(settings, "LABEL_PRINTER_URI", "")
        if not uri:
            raise CommandError("LABEL_PRINTER_URI is empty; set it in .env or pass --uri.")
        timeout = getattr(settings, "LABEL_PRINTER_TIMEOUT", 30)
        self.stdout.write(f"URI: {uri}")

        try:
            resp = ipp_get_printer_attributes(uri, timeout=timeout)
        except PrintError as exc:
            raise CommandError(str(exc)) from exc

        model = resp.first("printer-make-and-model") or resp.first("printer-info") or "?"
        state = resp.first("printer-state")
        reasons = ", ".join(str(r) for r in resp.all("printer-state-reasons")) or "-"
        formats = [str(f) for f in resp.all("document-format-supported")]
        media = ", ".join(str(m) for m in resp.all("media-ready")) or "-"
        self.stdout.write(f"Printer: {resp.first('printer-name')} ({model})")
        self.stdout.write(f"State: {PRINTER_STATES.get(state, state)}; reasons: {reasons}")
        self.stdout.write(f"Accepting jobs: {resp.first('printer-is-accepting-jobs')}")
        self.stdout.write(f"Formats: {', '.join(formats) or '-'}")
        self.stdout.write(f"Media ready: {media}")
        if formats and PWG_RASTER_FORMAT not in formats:
            self.stderr.write(f"Warning: printer does not list {PWG_RASTER_FORMAT}.")

        if not options["test_page"]:
            return

        from inventory.labels import LABEL_SIZES, render_label_png

        key = options["size"]
        if key not in LABEL_SIZES:
            raise CommandError(f"Unknown size {key!r}; one of {', '.join(LABEL_SIZES)}.")
        size = LABEL_SIZES[key]
        png = render_label_png(
            "https://example.invalid/i/1/",
            "Test label",
            "#0001",
            "OST / Test",
            size,
            barcode_data="#0001",
        )
        try:
            result = ipp_print_job(
                uri,
                png_to_pwg_raster([png]),
                job_name=f"OST test label {size.key}",
                user_name="check_label_printer",
                timeout=timeout,
            )
        except PrintError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Test label sent: job #{result.job_id}, state {result.job_state}")
