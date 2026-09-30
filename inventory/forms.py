from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from inventory.images import process_item_photo
from inventory.validators import reject_newlines, validate_optional_email_or_text

from .models import MAX_CATEGORIES, Category, Item, Loan, Location, Project


CATEGORY_SLOTS = tuple(f"category_{i}" for i in range(1, MAX_CATEGORIES + 1))
CATEGORY_PICK_FIELD = "category_pick"


def _posted_list(data, name: str) -> list[str]:
    if data is None:
        return []
    if hasattr(data, "getlist"):
        values = data.getlist(name)
    else:
        value = data.get(name)
        if value is None:
            values = []
        elif isinstance(value, (list, tuple)):
            values = list(value)
        else:
            values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _category_widget(placeholder: str) -> forms.TextInput:
    return forms.TextInput(
        attrs={
            "autocomplete": "off",
            "placeholder": placeholder,
        }
    )


class RoomScopedPlaceSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None and instance.parent_id:
            option["attrs"]["data-room"] = str(instance.parent_id)
        return option


def configure_room_place_fields(form, location=None):
    """Set up a form's `room` and `place` selects, preselecting `location`."""
    room = form.fields["room"]
    place = form.fields["place"]
    room.queryset = Location.objects.filter(parent__isnull=True).order_by("name")
    room.label_from_instance = lambda obj: obj.name
    place.queryset = (
        Location.objects.exclude(parent=None).select_related("parent").order_by("parent__name", "name")
    )
    place.label_from_instance = lambda obj: obj.name
    place.widget.attrs["data-room-select"] = form["room"].auto_id
    if location and location.pk:
        if location.parent_id:
            room.initial = location.parent_id
            place.initial = location.pk
        else:
            room.initial = location.pk


def configure_installed_in_field(field, item=None, data=None, name="installed_in"):
    """Validate against all legal hosts; render only empty + the current choice."""
    host_qs = Item.objects.filter(is_active=True).order_by("name")
    if item and item.pk:
        exclude_pks = [item.pk, *item.installed_part_pks()]
        host_qs = host_qs.exclude(pk__in=exclude_pks)
        if item.installed_in_id:
            host_qs = Item.objects.filter(
                Q(pk__in=host_qs.values("pk")) | Q(pk=item.installed_in_id)
            ).order_by("name")
    field.queryset = host_qs
    field.required = False
    field.empty_label = "Not mounted on another item"
    field.label_from_instance = lambda obj: f"{obj.inventory_number} {obj.name}"
    choices = [("", "Not mounted on another item")]
    selected_pk = None
    if data is not None:
        raw = data.get(name)
        if raw not in (None, ""):
            try:
                selected_pk = int(raw)
            except (TypeError, ValueError):
                selected_pk = None
    elif item and item.installed_in_id:
        selected_pk = item.installed_in_id
    if selected_pk:
        host = Item.objects.filter(pk=selected_pk).first()
        if host:
            choices.append((str(host.pk), f"{host.inventory_number} {host.name}"))
    field.choices = choices


class InstalledInForm(forms.Form):
    installed_in = forms.ModelChoiceField(queryset=Item.objects.none(), required=False)

    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item
        configure_installed_in_field(
            self.fields["installed_in"], item, self.data if self.is_bound else None
        )


class SplitItemForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, initial=1, label="Units")
    room = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label="Room",
        empty_label="Select a room",
    )
    place = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label="Place",
        empty_label="Whole room",
        widget=RoomScopedPlaceSelect,
    )
    installed_in = forms.ModelChoiceField(queryset=Item.objects.none(), required=False)

    def __init__(self, *args, item, **kwargs):
        kwargs.setdefault("prefix", "split")
        super().__init__(*args, **kwargs)
        self.item = item
        self.fields["quantity"].widget.attrs.update(
            {"max": max(item.quantity - 1, 1), "inputmode": "numeric"}
        )
        configure_room_place_fields(self, item.location)
        configure_installed_in_field(
            self.fields["installed_in"],
            item,
            self.data if self.is_bound else {},
            name=self.add_prefix("installed_in"),
        )

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity >= self.item.quantity:
            raise ValidationError(
                f"Split off at most {self.item.quantity - 1} of {self.item.quantity} units."
            )
        return quantity

    def clean(self):
        cleaned = super().clean()
        room = cleaned.get("room")
        place = cleaned.get("place")
        if not cleaned.get("installed_in") and not room:
            self.add_error("room", "Select a room or an item to mount on.")
        if place and room and place.parent_id != room.pk:
            self.add_error("place", "Place must belong to the selected room.")
        cleaned["location"] = place or room
        return cleaned


class SameTypeForm(forms.Form):
    same_as = forms.ModelChoiceField(queryset=Item.objects.none(), label="Same type as")

    def __init__(self, *args, item, **kwargs):
        kwargs.setdefault("prefix", "type")
        super().__init__(*args, **kwargs)
        field = self.fields["same_as"]
        field.queryset = Item.objects.filter(is_active=True).exclude(pk=item.pk)
        field.label_from_instance = lambda obj: f"{obj.inventory_number} {obj.name}"
        # Render only the placeholder; the item picker adds the chosen option.
        field.choices = [("", "Choose an item")]


class MergeItemForm(forms.Form):
    into = forms.ModelChoiceField(queryset=Item.objects.none(), label="Merge into")

    def __init__(self, *args, item, **kwargs):
        kwargs.setdefault("prefix", "merge")
        super().__init__(*args, **kwargs)
        field = self.fields["into"]
        field.queryset = (
            item.same_type_items()
            .exclude(pk__in=Loan.objects.filter(returned_at__isnull=True).values("item_id"))
            .select_related("location", "location__parent")
        )
        field.label_from_instance = lambda obj: (
            f"{obj.inventory_number} · {obj.quantity_display}× · {obj.location.path_display()}"
        )
        field.empty_label = None


class ItemForm(forms.ModelForm):
    room = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        label="Room",
        empty_label="Select a room",
    )
    place = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label="Place",
        empty_label="Whole room",
        widget=RoomScopedPlaceSelect,
    )
    category_1 = forms.CharField(
        required=False,
        max_length=100,
        label="Category 1",
        widget=_category_widget("New name, if needed"),
    )
    category_2 = forms.CharField(
        required=False,
        max_length=100,
        label="Category 2",
        widget=_category_widget("Optional"),
    )
    category_3 = forms.CharField(
        required=False,
        max_length=100,
        label="Category 3",
        widget=_category_widget("Optional"),
    )
    category_4 = forms.CharField(
        required=False,
        max_length=100,
        label="Category 4",
        widget=_category_widget("Optional"),
    )
    project_name = forms.CharField(
        required=False,
        label="Project",
        widget=forms.TextInput(
            attrs={
                "list": "project-suggestions",
                "autocomplete": "off",
                "placeholder": "e.g. Sternwarte 2026",
            }
        ),
    )

    class Meta:
        model = Item
        fields = [
            "name",
            "description",
            "quantity",
            "quantity_is_approximate",
            "container",
            "installed_in",
            "comment",
            "photo",
        ]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1, "required": True}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "comment": forms.Textarea(attrs={"rows": 2}),
            "container": forms.TextInput(
                attrs={
                    "list": "container-suggestions",
                    "autocomplete": "off",
                    "placeholder": "e.g. Crate 4, camera bag",
                }
            ),
            "photo": forms.ClearableFileInput(
                attrs={"accept": "image/*", "capture": "environment"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["quantity"].required = True
        self.fields["quantity_is_approximate"].label = "Approximate count"
        self.fields["room"].required = False
        configure_room_place_fields(self, getattr(self.instance, "location", None))
        if self.instance and self.instance.pk:
            if self.instance.project_id:
                self.fields["project_name"].initial = self.instance.project.name
        configure_installed_in_field(
            self.fields["installed_in"],
            self.instance if self.instance.pk else None,
            self.data if self.is_bound else None,
        )

    def category_fields(self):
        return [self[name] for name in CATEGORY_SLOTS]

    def category_limit(self) -> int:
        return MAX_CATEGORIES

    def picked_category_names(self) -> list[str]:
        if self.is_bound:
            return _posted_list(self.data, CATEGORY_PICK_FIELD)
        if self.instance and self.instance.pk:
            return [cat.name for cat in self.instance.categories.all()[:MAX_CATEGORIES]]
        return []

    def picked_category_keys(self) -> set[str]:
        return {name.lower() for name in self.picked_category_names()}

    def clean_name(self):
        name = self.cleaned_data.get("name") or ""
        reject_newlines(name, "Name")
        return name

    def clean_container(self):
        container = (self.cleaned_data.get("container") or "").strip()
        reject_newlines(container, "Container")
        return container

    def clean_project_name(self):
        name = self.cleaned_data.get("project_name") or ""
        reject_newlines(name, "Project")
        return name.strip()

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if not photo:
            return photo
        if getattr(photo, "_processed_item_photo", False):
            return photo
        from django.core.files.uploadedfile import UploadedFile

        if not isinstance(photo, UploadedFile):
            return photo
        processed = process_item_photo(photo)
        processed._processed_item_photo = True
        return processed

    def clean(self):
        cleaned = super().clean()
        installed_in = cleaned.get("installed_in")
        room = cleaned.get("room")
        place = cleaned.get("place")
        if installed_in and self.instance.pk and installed_in.pk == self.instance.pk:
            self.add_error("installed_in", "An item cannot be mounted on itself.")
        elif not installed_in and not room:
            self.add_error("room", "Select a room.")
        if place and room and place.parent_id != room.pk:
            self.add_error("place", "Place must belong to the selected room.")
        names = []
        seen = set()

        def add_category(raw: str, error_slot: str) -> None:
            raw = (raw or "").strip()
            if not raw:
                return
            try:
                reject_newlines(raw, "Category")
            except ValidationError as exc:
                self.add_error(error_slot, exc)
                return
            key = raw.lower()
            if key in seen:
                return
            seen.add(key)
            names.append(raw)

        if self.is_bound:
            for raw in _posted_list(self.data, CATEGORY_PICK_FIELD):
                add_category(raw, "category_1")
        for slot in CATEGORY_SLOTS:
            raw = (cleaned.get(slot) or "").strip()
            cleaned[slot] = raw
            add_category(raw, slot)
        if len(names) > MAX_CATEGORIES:
            self.add_error(
                "category_1",
                f"At most {MAX_CATEGORIES} categories are allowed.",
            )
        elif not names and not any(self.has_error(slot) for slot in CATEGORY_SLOTS):
            self.add_error("category_1", "Select or add at least one category.")
        cleaned["category_names"] = names
        return cleaned

    def save(self, commit=True):
        item = super().save(commit=False)
        room = self.cleaned_data["room"]
        place = self.cleaned_data.get("place")
        if item.installed_in_id:
            item.location = item.installed_in.location
        else:
            item.location = place or room
        project_name = self.cleaned_data.get("project_name", "")
        project, _ = Project.get_or_create_by_name(project_name)
        item.project = project if project_name.strip() else None
        if commit:
            item.save()
            cats = []
            seen = set()
            for name in self.cleaned_data.get("category_names") or []:
                cat, _ = Category.get_or_create_by_name(name)
                if cat and cat.pk not in seen:
                    cats.append(cat)
                    seen.add(cat.pk)
            item.categories.set(cats)
        return item


class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ["borrower_name", "borrower_contact", "due_date", "note"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_borrower_name(self):
        name = self.cleaned_data.get("borrower_name") or ""
        reject_newlines(name, "Borrower name")
        return name

    def clean_borrower_contact(self):
        return validate_optional_email_or_text(self.cleaned_data.get("borrower_contact") or "")

    def clean_note(self):
        note = self.cleaned_data.get("note") or ""
        reject_newlines(note, "Note")
        return note


class RoomForm(forms.Form):
    name = forms.CharField(max_length=200, label="Room")

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        reject_newlines(name, "Room")
        if not name:
            raise ValidationError("Room is required.")
        return name


class PlaceForm(forms.Form):
    room = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        label="Room",
        empty_label="Select a room",
    )
    name = forms.CharField(max_length=200, label="Place")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = Location.objects.filter(parent__isnull=True).order_by(
            "name"
        )
        self.fields["room"].label_from_instance = lambda obj: obj.name

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        reject_newlines(name, "Place")
        if not name:
            raise ValidationError("Place is required.")
        return name
