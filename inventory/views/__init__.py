from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, OrderBy, Prefetch, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.permissions import (
    ReadRequiredMixin,
    WriteRequiredMixin,
    user_can_delete,
    user_can_see_inactive,
    user_can_see_loan_pii,
    user_can_write,
    write_required,
)
from inventory.forms import InstalledInForm, ItemForm, LoanForm, PlaceForm, RoomForm
from inventory.images import process_item_photo
from inventory.labels import (
    LABEL_CODE_SESSION_KEY,
    LABEL_SIZE_LIST,
    LABEL_SIZE_SESSION_KEY,
    DEFAULT_SIZE_KEY,
    get_label_code,
    get_label_size,
)
from inventory.models import Category, Item, Loan, Location, Project
from inventory.policy import visible_items
from inventory.search import _inventory_number_q, filter_items
from inventory.stocktake import get_open_stocktake, record_item_scan, set_active_stocktake


def _item_form_catalogs():
    return {
        "categories": Category.objects.all(),
        "projects": Project.objects.all(),
        "containers": (
            Item.objects.exclude(container="")
            .order_by("container")
            .values_list("container", flat=True)
            .distinct()
        ),
    }


class SearchView(ReadRequiredMixin, ListView):
    model = Item
    template_name = "inventory/search.html"
    context_object_name = "items"
    paginate_by = 25

    def get_queryset(self):
        qs = Item.objects.select_related(
            "location", "location__parent", "project", "installed_in"
        ).prefetch_related(
            "categories",
            Prefetch(
                "loans",
                queryset=Loan.objects.filter(returned_at__isnull=True),
                to_attr="open_loans",
            ),
        )
        return filter_items(
            qs,
            q=self.request.GET.get("q", ""),
            category=self.request.GET.get("category", ""),
            location=self.request.GET.get("location", ""),
            project=self.request.GET.get("project", ""),
            container=self.request.GET.get("container", ""),
            on_loan=self.request.GET.get("on_loan") == "1",
            include_inactive=self.request.GET.get("inactive") == "1"
            and user_can_see_inactive(self.request.user),
        )

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["inventory/partials/search_results.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["selected_category"] = self.request.GET.get("category", "")
        ctx["selected_location"] = self.request.GET.get("location", "")
        ctx["selected_project"] = self.request.GET.get("project", "")
        ctx["selected_container"] = self.request.GET.get("container", "")
        ctx["on_loan"] = self.request.GET.get("on_loan") == "1"
        ctx["categories"] = Category.objects.all()
        ctx["locations"] = Location.objects.all().select_related("parent")
        ctx["projects"] = Project.objects.all()
        ctx["containers"] = (
            Item.objects.exclude(container="")
            .order_by("container")
            .values_list("container", flat=True)
            .distinct()
        )
        return ctx


class ItemDetailView(ReadRequiredMixin, DetailView):
    model = Item
    template_name = "inventory/item_detail.html"
    context_object_name = "item"

    def get_queryset(self):
        return visible_items(
            self.request.user,
            Item.objects.select_related(
                "location",
                "location__parent",
                "project",
                "created_by",
                "updated_by",
                "installed_in",
            ).prefetch_related("categories", "loans__recorded_by", "installed_parts"),
        )

    def get(self, request, *args, **kwargs):
        if (
            getattr(request.resolver_match, "url_name", "") == "item_short"
            and user_can_write(request.user)
        ):
            stocktake = get_open_stocktake(request)
            if stocktake:
                self.object = self.get_object()
                record_item_scan(stocktake, self.object, request.user)
                set_active_stocktake(request, stocktake)
                messages.success(
                    request,
                    f"Recorded {self.object.inventory_number} {self.object.name}.",
                )
                return redirect("inventory:stocktake_detail", pk=stocktake.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["loan_form"] = LoanForm()
        ctx["loans"] = self.object.loans.all()
        ctx["label_sizes"] = LABEL_SIZE_LIST
        ctx["selected_size"] = self.request.session.get(
            LABEL_SIZE_SESSION_KEY, DEFAULT_SIZE_KEY
        )
        ctx["selected_code"] = get_label_code(
            self.request.session.get(LABEL_CODE_SESSION_KEY),
            get_label_size(ctx["selected_size"]),
        )
        ctx["install_form"] = InstalledInForm(item=self.object)
        return ctx


class ItemCreateView(WriteRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "inventory/item_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Item created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:item_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_item_form_catalogs())
        ctx["title"] = "Add item"
        return ctx


class ItemUpdateView(WriteRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = "inventory/item_form.html"

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Item saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:item_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_item_form_catalogs())
        ctx["title"] = "Edit item"
        return ctx


@write_required
def item_deactivate(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    item.is_active = False
    item.updated_by = request.user
    item.save(update_fields=["is_active", "updated_by", "updated_at"])
    messages.info(request, "Item deactivated.")
    return redirect("inventory:item_detail", pk=pk)


@write_required
def item_reactivate(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    item.is_active = True
    item.updated_by = request.user
    item.save(update_fields=["is_active", "updated_by", "updated_at"])
    messages.success(request, "Item reactivated.")
    return redirect("inventory:item_detail", pk=pk)


@write_required
def item_delete(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if not user_can_delete(request.user):
        messages.error(request, "You cannot permanently delete items.")
        return redirect("inventory:item_detail", pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    try:
        item.delete()
    except ProtectedError:
        messages.error(
            request,
            "Reassign or remove items mounted here before deleting this item.",
        )
        return redirect("inventory:item_detail", pk=pk)
    messages.warning(request, "Item permanently deleted.")
    return redirect("inventory:search")


@write_required
def item_host_lookup(request):
    if request.method != "GET":
        return HttpResponseBadRequest("GET required")
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})
    qs = Item.objects.filter(is_active=True).select_related("location", "location__parent")
    raw_exclude = request.GET.get("exclude") or ""
    if raw_exclude.isdigit():
        skip = [int(raw_exclude)]
        source = Item.objects.filter(pk=skip[0]).first()
        if source:
            skip.extend(source.installed_part_pks())
        qs = qs.exclude(pk__in=skip)
    qs = qs.filter(Q(name__icontains=q) | _inventory_number_q(q)).order_by("name")[:20]
    return JsonResponse(
        {
            "results": [
                {
                    "id": item.pk,
                    "label": f"{item.inventory_number} {item.name}",
                    "location": item.location.path_display(),
                }
                for item in qs
            ]
        }
    )


@write_required
def item_install(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    form = InstalledInForm(request.POST, item=item)
    if not form.is_valid():
        messages.error(request, "Could not update the host item.")
        return redirect("inventory:item_detail", pk=pk)
    host = form.cleaned_data.get("installed_in")
    item.installed_in = host
    if host:
        item.location = host.location
    item.updated_by = request.user
    try:
        item.full_clean()
    except ValidationError as exc:
        err = exc.message_dict.get("installed_in") if getattr(exc, "message_dict", None) else None
        messages.error(request, err[0] if err else "Could not update the host item.")
        return redirect("inventory:item_detail", pk=pk)
    item.save()
    if host:
        messages.success(
            request, f"Mounted on {host.inventory_number} {host.name}."
        )
    else:
        messages.success(request, "No longer mounted on another item.")
    return redirect("inventory:item_detail", pk=pk)


@write_required
def loan_create(request, pk):
    item = get_object_or_404(Item, pk=pk, is_active=True)
    if item.is_lent:
        messages.error(request, "Item is already on loan.")
        return redirect("inventory:item_detail", pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    form = LoanForm(request.POST)
    if form.is_valid():
        loan = form.save(commit=False)
        loan.item = item
        loan.recorded_by = request.user
        loan.save()
        messages.success(request, "Loan recorded.")
    else:
        messages.error(request, "Could not create loan. Check the form.")
    return redirect("inventory:item_detail", pk=pk)


@write_required
def loan_return(request, pk):
    loan = get_object_or_404(Loan, pk=pk, returned_at__isnull=True)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    loan.return_item()
    messages.success(request, "Item returned.")
    return redirect("inventory:item_detail", pk=loan.item_id)


@write_required
def still_here(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    item.last_seen_at = timezone.now()
    item.updated_by = request.user
    item.save(update_fields=["last_seen_at", "updated_by", "updated_at"])
    hx = request.headers.get("HX-Request")
    if not hx:
        messages.success(request, "Marked as still here.")
    if hx:
        return render(request, "inventory/partials/still_here_ok.html", {"item": item})
    return redirect("inventory:item_detail", pk=pk)


@write_required
def item_photo(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    uploaded = request.FILES.get("photo")
    if not uploaded:
        messages.error(request, "Take or choose a photo first.")
        return redirect("inventory:item_detail", pk=pk)
    try:
        processed = process_item_photo(uploaded)
    except ValidationError as exc:
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        messages.error(request, message)
        return redirect("inventory:item_detail", pk=pk)
    old_name = item.photo.name if item.photo else ""
    item.photo = processed
    item.updated_by = request.user
    item.save(update_fields=["photo", "updated_by", "updated_at"])
    if old_name and old_name != item.photo.name:
        item.photo.storage.delete(old_name)
    messages.success(request, "Photo saved.")
    return redirect("inventory:item_detail", pk=pk)


class CurrentLoansView(ReadRequiredMixin, ListView):
    model = Loan
    template_name = "inventory/current_loans.html"
    context_object_name = "loans"
    paginate_by = 50

    def get_queryset(self):
        return (
            Loan.objects.filter(returned_at__isnull=True)
            .select_related("item", "item__location", "recorded_by")
            .order_by("due_date")
        )


class LoanHistoryView(ReadRequiredMixin, ListView):
    model = Loan
    template_name = "inventory/loan_history.html"
    context_object_name = "loans"
    paginate_by = 50

    def get_queryset(self):
        qs = Loan.objects.select_related("item", "recorded_by").order_by("-borrowed_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            filters = Q(item__name__icontains=q)
            if user_can_see_loan_pii(self.request.user):
                filters |= Q(borrower_name__icontains=q) | Q(borrower_contact__icontains=q)
            qs = qs.filter(filters)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


class NotSeenRecentlyView(ReadRequiredMixin, ListView):
    model = Item
    template_name = "inventory/not_seen.html"
    context_object_name = "items"
    paginate_by = 50

    def get_queryset(self):
        return (
            Item.objects.filter(is_active=True)
            .select_related("location", "location__parent", "project", "installed_in")
            .order_by(OrderBy(F("last_seen_at"), descending=False, nulls_first=True))
        )


class LocationListView(ReadRequiredMixin, ListView):
    model = Location
    template_name = "inventory/locations.html"
    context_object_name = "rooms"

    def get_queryset(self):
        places = Location.objects.annotate(item_count=Count("items")).order_by("name")
        return (
            Location.objects.filter(parent__isnull=True)
            .prefetch_related(Prefetch("children", queryset=places))
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["room_form"] = RoomForm()
        ctx["place_form"] = PlaceForm()
        return ctx


@write_required
def location_add_room(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    form = RoomForm(request.POST)
    if form.is_valid():
        room, created = Location.get_or_create_room(form.cleaned_data["name"])
        if created:
            messages.success(request, f"Room {room.name} added.")
        else:
            messages.info(request, f"Room {room.name} already exists.")
    else:
        messages.error(request, "Could not add room.")
    return redirect("inventory:locations")


@write_required
def location_add_place(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    form = PlaceForm(request.POST)
    if form.is_valid():
        place, created = Location.get_or_create_place(
            form.cleaned_data["room"], form.cleaned_data["name"]
        )
        if created:
            messages.success(
                request, f"Place {place.path_display()} added."
            )
        else:
            messages.info(request, f"Place {place.path_display()} already exists.")
    else:
        messages.error(request, "Could not add place. Choose a room and a name.")
    return redirect("inventory:locations")


@write_required
def location_rename_room(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    room = get_object_or_404(Location, pk=pk, parent__isnull=True)
    form = RoomForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not rename room.")
        return redirect("inventory:locations")
    name = form.cleaned_data["name"]
    clash = (
        Location.objects.filter(parent__isnull=True, name__iexact=name)
        .exclude(pk=room.pk)
        .exists()
    )
    if clash:
        messages.error(request, f"Room {name} already exists.")
        return redirect("inventory:locations")
    if room.name != name:
        room.name = name
        room.save(update_fields=["name"])
        messages.success(request, f"Room renamed to {room.name}.")
    return redirect("inventory:locations")


@write_required
def location_delete_place(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    place = get_object_or_404(Location, pk=pk, parent__isnull=False)
    room = place.parent
    name = place.name
    with transaction.atomic():
        moved = Item.objects.filter(location=place).update(
            location=room,
            updated_at=timezone.now(),
            updated_by=request.user,
        )
        place.delete()
    if moved:
        messages.success(
            request,
            f"Place {name} removed. {moved} item(s) now in {room.name}.",
        )
    else:
        messages.success(request, f"Place {name} removed.")
    return redirect("inventory:locations")


class LocationDetailView(ReadRequiredMixin, DetailView):
    model = Location
    template_name = "inventory/location_detail.html"
    context_object_name = "location"

    def get_queryset(self):
        return Location.objects.select_related("parent")

    def get(self, request, *args, **kwargs):
        if (
            getattr(request.resolver_match, "url_name", "") == "location_short"
            and user_can_write(request.user)
        ):
            stocktake = get_open_stocktake(request)
            if stocktake:
                self.object = self.get_object()
                stocktake.current_location = self.object
                stocktake.save(update_fields=["current_location"])
                set_active_stocktake(request, stocktake)
                messages.success(
                    request, f"Now counting {self.object.path_display()}."
                )
                return redirect("inventory:stocktake_detail", pk=stocktake.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ids = self.object.get_descendant_ids()
        ctx["items"] = (
            Item.objects.filter(is_active=True, location_id__in=ids)
            .select_related("location", "location__parent", "project", "installed_in")
            .order_by("name")
        )
        ctx["children"] = self.object.children.order_by("name")
        return ctx
