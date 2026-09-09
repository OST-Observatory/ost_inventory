from .permissions import (
    user_can_admin,
    user_can_delete,
    user_can_import,
    user_can_print_labels,
    user_can_read,
    user_can_see_inactive,
    user_can_see_loan_pii,
    user_can_write,
)


def permissions(request):
    user = getattr(request, "user", None)
    return {
        "can_read": user_can_read(user),
        "can_write": user_can_write(user),
        "can_admin": user_can_admin(user),
        "can_delete": user_can_delete(user),
        "can_import": user_can_import(user),
        "can_labels": user_can_print_labels(user),
        "can_see_loan_pii": user_can_see_loan_pii(user),
        "can_see_inactive": user_can_see_inactive(user),
    }
