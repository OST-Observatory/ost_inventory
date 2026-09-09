from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied

from .acl import (
    DELETE,
    IMPORT,
    INACTIVE,
    LABELS,
    LOAN_PII,
    MANAGE_ACL,
    READ,
    WRITE,
)
from .models import GroupCapability


def user_capabilities(user) -> frozenset[str]:
    if not user or not getattr(user, "is_authenticated", False):
        return frozenset()
    cached = getattr(user, "_inventory_capabilities", None)
    if cached is not None:
        return cached
    if user.is_superuser:
        from .acl import CAPABILITY_CODES

        result = frozenset(CAPABILITY_CODES)
    else:
        result = frozenset(
            GroupCapability.objects.filter(group__user=user).values_list(
                "capability", flat=True
            )
        )
    user._inventory_capabilities = result
    return result


def user_has_capability(user, capability: str) -> bool:
    return capability in user_capabilities(user)


def user_can_read(user) -> bool:
    return user_has_capability(user, READ)


def user_can_write(user) -> bool:
    return user_has_capability(user, WRITE)


def user_can_admin(user) -> bool:
    return user_has_capability(user, MANAGE_ACL)


def user_can_delete(user) -> bool:
    return user_has_capability(user, DELETE)


def user_can_import(user) -> bool:
    return user_has_capability(user, IMPORT)


def user_can_print_labels(user) -> bool:
    return user_has_capability(user, LABELS)


def user_can_see_loan_pii(user) -> bool:
    return user_has_capability(user, LOAN_PII)


def user_can_see_inactive(user) -> bool:
    return user_has_capability(user, INACTIVE)


class ReadRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_can_read(self.request.user)


class WriteRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_can_write(self.request.user)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_can_admin(self.request.user)


def _require_capability(capability):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not user_has_capability(request.user, capability):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def read_required(view_func):
    return _require_capability(READ)(view_func)


def write_required(view_func):
    return _require_capability(WRITE)(view_func)


def admin_required(view_func):
    return _require_capability(MANAGE_ACL)(view_func)


def import_required(view_func):
    return _require_capability(IMPORT)(view_func)


def labels_required(view_func):
    return _require_capability(LABELS)(view_func)
