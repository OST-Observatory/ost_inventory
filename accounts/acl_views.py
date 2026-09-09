from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from .acl import CAPABILITIES, CAPABILITY_CODES, MANAGE_ACL
from .forms import AddMemberForm, GroupNameForm
from .models import GroupCapability, is_protected_group
from .permissions import AdminRequiredMixin, admin_required

User = get_user_model()


class AccessControlView(AdminRequiredMixin, ListView):
    model = Group
    template_name = "accounts/access.html"
    context_object_name = "groups"

    def get_queryset(self):
        return Group.objects.prefetch_related("inventory_capabilities").order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for group in ctx["groups"]:
            granted = {row.capability for row in group.inventory_capabilities.all()}
            checks = [
                (code, label, code in granted) for code, label in CAPABILITIES
            ]
            rows.append((group, checks))
        ctx["rows"] = rows
        ctx["capabilities"] = CAPABILITIES
        return ctx


@admin_required
def access_save(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    groups = list(Group.objects.all())
    proposed = {}
    for group in groups:
        caps = set()
        for code in CAPABILITY_CODES:
            key = f"cap_{group.pk}_{code}"
            if request.POST.get(key):
                caps.add(code)
        proposed[group.pk] = caps

    if not request.user.is_superuser:
        user_group_ids = set(request.user.groups.values_list("pk", flat=True))
        still_admin = any(MANAGE_ACL in proposed.get(gid, set()) for gid in user_group_ids)
        if not still_admin:
            messages.error(
                request,
                "You cannot remove your own permission to manage access.",
            )
            return redirect("accounts:access")

    with transaction.atomic():
        for group in groups:
            GroupCapability.objects.filter(group=group).exclude(
                capability__in=proposed[group.pk]
            ).delete()
            existing = set(
                GroupCapability.objects.filter(group=group).values_list(
                    "capability", flat=True
                )
            )
            for cap in proposed[group.pk] - existing:
                GroupCapability.objects.create(group=group, capability=cap)
    messages.success(request, "Access control saved.")
    return redirect("accounts:access")


class GroupListView(AdminRequiredMixin, ListView):
    model = Group
    template_name = "accounts/groups.html"
    context_object_name = "groups"

    def get_queryset(self):
        return Group.objects.annotate(member_count=Count("user")).order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = GroupNameForm()
        ctx["protected_names"] = {g.name for g in ctx["groups"] if is_protected_group(g)}
        return ctx


@admin_required
def group_add(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    form = GroupNameForm(request.POST)
    if form.is_valid():
        Group.objects.create(name=form.cleaned_data["name"])
        messages.success(request, "Group added. Assign permissions under Access control.")
        return redirect("accounts:groups")
    messages.error(request, "Could not add group.")
    return redirect("accounts:groups")


@admin_required
def group_detail(request, pk):
    group = get_object_or_404(Group, pk=pk)
    members = group.user_set.order_by("username")
    return render(
        request,
        "accounts/group_detail.html",
        {
            "group": group,
            "members": members,
            "form": AddMemberForm(),
            "protected": is_protected_group(group),
        },
    )


@admin_required
def group_add_member(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    group = get_object_or_404(Group, pk=pk)
    form = AddMemberForm(request.POST)
    if form.is_valid():
        try:
            user = User.objects.get(username__iexact=form.cleaned_data["username"])
        except User.DoesNotExist:
            messages.error(request, "No user with that username.")
        else:
            group.user_set.add(user)
            messages.success(request, f"{user.username} added to {group.name}.")
    else:
        messages.error(request, "Could not add member.")
    return redirect("accounts:group_detail", pk=group.pk)


@admin_required
def group_remove_member(request, pk, user_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    group = get_object_or_404(Group, pk=pk)
    user = get_object_or_404(User, pk=user_id)
    group.user_set.remove(user)
    messages.success(request, f"{user.username} removed from {group.name}.")
    return redirect("accounts:group_detail", pk=group.pk)


@admin_required
def group_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    group = get_object_or_404(Group, pk=pk)
    if is_protected_group(group):
        messages.error(request, "This group is tied to login roles and cannot be deleted.")
        return redirect("accounts:groups")
    name = group.name
    group.delete()
    messages.success(request, f"Group {name} deleted.")
    return redirect("accounts:groups")
