from django.conf import settings
from django.utils import timezone

from accounts.permissions import user_can_read, user_can_write
from inventory.models import Loan
from inventory.stocktake import SESSION_KEY


def nav(request):
    user = getattr(request, "user", None)
    count = 0
    if user_can_read(user):
        count = Loan.objects.filter(
            returned_at__isnull=True,
            due_date__lt=timezone.localdate(),
        ).count()
    match = getattr(request, "resolver_match", None)
    active_id = None
    if user_can_write(user):
        active_id = request.session.get(SESSION_KEY)
    printer_name = ""
    if getattr(settings, "LABEL_PRINTER_URI", ""):
        printer_name = getattr(settings, "LABEL_PRINTER_NAME", "") or "Label printer"
    return {
        "overdue_loan_count": count,
        "current_url_name": getattr(match, "url_name", "") or "",
        "current_url_namespace": getattr(match, "namespace", "") or "",
        "active_stocktake_id": active_id,
        "label_printer_name": printer_name,
    }
