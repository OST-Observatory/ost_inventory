import uuid
from collections import deque
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from inventory.images import item_photo_upload_to
from inventory.validators import reject_newlines, validate_optional_email_or_text

MAX_CATEGORIES = 4


class Location(models.Model):
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["parent"])]

    def __str__(self):
        return self.path_display()

    def path_display(self) -> str:
        parts = []
        node = self
        seen = set()
        while node is not None and node.pk not in seen:
            seen.add(node.pk)
            parts.append(node.name)
            node = node.parent
        return " / ".join(reversed(parts))

    def get_descendant_ids(self):
        """Return pk list including self and all descendants."""
        ids = [self.pk]
        children = list(Location.objects.filter(parent_id=self.pk).values_list("pk", flat=True))
        queue = list(children)
        while queue:
            current = queue.pop()
            ids.append(current)
            queue.extend(
                Location.objects.filter(parent_id=current).values_list("pk", flat=True)
            )
        return ids

    @property
    def is_room(self) -> bool:
        return self.parent_id is None

    def clean(self):
        super().clean()
        reject_newlines(self.name, "Name")
        if self.parent_id and self.parent and self.parent.parent_id:
            from django.core.exceptions import ValidationError

            raise ValidationError("A place cannot contain other places. Use room + place.")

    @classmethod
    def get_or_create_room(cls, raw_name: str):
        name = (raw_name or "").strip()
        if not name:
            return None, False
        existing = cls.objects.filter(parent__isnull=True, name__iexact=name).first()
        if existing:
            return existing, False
        return cls.objects.create(name=name, parent=None), True

    @classmethod
    def get_or_create_place(cls, room, raw_name: str):
        name = (raw_name or "").strip()
        if not room or not name:
            return None, False
        existing = cls.objects.filter(parent=room, name__iexact=name).first()
        if existing:
            return existing, False
        return cls.objects.create(name=name, parent=room), True


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_by_name(cls, raw_name: str):
        name = (raw_name or "").strip()
        if not name:
            return None, False
        existing = cls.objects.filter(name__iexact=name).first()
        if existing:
            return existing, False
        return cls.objects.create(name=name), True


class Project(models.Model):
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="project_name_ci_unique"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_by_name(cls, raw_name: str):
        name = (raw_name or "").strip()
        if not name:
            return None, False
        existing = cls.objects.filter(name__iexact=name).first()
        if existing:
            return existing, False
        return cls.objects.create(name=name), True


class Item(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    quantity_is_approximate = models.BooleanField(
        default=False,
        help_text="Check if the count is estimated (e.g. screws, cable ties).",
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="items"
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="items")
    container = models.CharField(
        max_length=120,
        blank=True,
        help_text="Box, crate, or bag this item is stored in.",
    )
    installed_in = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="installed_parts",
        verbose_name="mounted on",
        help_text="Another inventory item this one is mounted on.",
    )
    unit_group = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        help_text="Items sharing this value are units of the same type.",
    )
    comment = models.TextField(blank=True)
    photo = models.ImageField(upload_to=item_photo_upload_to, null=True, blank=True)
    categories = models.ManyToManyField(Category, blank=True, related_name="items")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="items_created"
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="items_updated"
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["location"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["last_seen_at"]),
            models.Index(fields=["container"]),
            models.Index(fields=["project"]),
            models.Index(fields=["installed_in"]),
            models.Index(fields=["unit_group"]),
        ]

    def __str__(self):
        return f"{self.inventory_number} {self.name}"

    @property
    def inventory_number(self) -> str:
        if self.pk is None:
            return "#????"
        return f"#{self.pk:04d}"

    @property
    def current_loan(self):
        return self.loans.filter(returned_at__isnull=True).first()

    @property
    def is_lent(self) -> bool:
        return self.current_loan is not None

    @property
    def quantity_display(self) -> str:
        if self.quantity_is_approximate:
            return f"~{self.quantity}"
        return str(self.quantity)

    @classmethod
    def lookup_by_ref(cls, raw: str):
        """Resolve an inventory number or numeric id such as '#0004' or '4'."""
        text = (raw or "").strip()
        if text.startswith("#"):
            text = text[1:].strip()
        if not text.isdigit():
            return None
        return cls.objects.filter(pk=int(text)).first()

    def installed_part_pks(self):
        pks = []
        queue = deque(self.installed_parts.values_list("pk", flat=True))
        while queue:
            pk = queue.popleft()
            pks.append(pk)
            queue.extend(
                type(self).objects.filter(installed_in_id=pk).values_list("pk", flat=True)
            )
        return pks

    def clean(self):
        super().clean()
        reject_newlines(self.name, "Name")
        reject_newlines(self.container, "Container")
        if not self.installed_in_id:
            return
        if self.pk and self.installed_in_id == self.pk:
            raise ValidationError(
                {"installed_in": "An item cannot be mounted on itself."}
            )
        host_id = self.installed_in_id
        seen = {self.pk} if self.pk else set()
        while host_id:
            if host_id in seen:
                raise ValidationError(
                    {"installed_in": "That would create a loop of mounted items."}
                )
            seen.add(host_id)
            host_id = (
                type(self)
                .objects.filter(pk=host_id)
                .values_list("installed_in_id", flat=True)
                .first()
            )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        previous_location_id = None
        if self.pk:
            previous_location_id = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("location_id", flat=True)
                .first()
            )
        if update_fields is None and self.installed_in_id:
            host_location_id = (
                type(self)
                .objects.filter(pk=self.installed_in_id)
                .values_list("location_id", flat=True)
                .first()
            )
            if host_location_id:
                self.location_id = host_location_id
        super().save(*args, **kwargs)
        if previous_location_id and previous_location_id != self.location_id:
            self._cascade_location_to_installed_parts()

    def _cascade_location_to_installed_parts(self):
        for pk in self.installed_part_pks():
            type(self).objects.filter(pk=pk).exclude(location_id=self.location_id).update(
                location_id=self.location_id
            )

    def mark_seen(self):
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at", "updated_at"])

    @transaction.atomic
    def split_off(self, quantity: int, user, *, location=None, installed_in=None):
        """Move `quantity` units into a new item with its own number.

        The new item copies name, description, project, categories and photo. It is
        mounted on `installed_in` (and follows its location) or stored at `location`.
        """
        if not 1 <= quantity < self.quantity:
            raise ValidationError(
                f"Choose between 1 and {self.quantity - 1} units to split off."
            )
        if installed_in is None and location is None:
            raise ValidationError("Choose a location or an item to mount on.")
        part = type(self)(
            name=self.name,
            description=self.description,
            quantity=quantity,
            quantity_is_approximate=self.quantity_is_approximate and quantity > 1,
            project=self.project,
            unit_group=self._ensure_unit_group(),
            location=installed_in.location if installed_in else location,
            installed_in=installed_in,
            comment=f"Split off from {self.inventory_number}.",
            last_seen_at=timezone.now(),
            created_by=user,
            updated_by=user,
        )
        if self.photo:
            # Own copy: deleting or replacing either item's photo removes its file.
            with self.photo.open("rb") as src:
                part.photo.save(Path(self.photo.name).name, File(src), save=False)
        part.full_clean(exclude=["photo"])
        part.save()
        part.categories.set(self.categories.all())
        self.quantity -= quantity
        self.updated_by = user
        self.save(update_fields=["quantity", "unit_group", "updated_by", "updated_at"])
        return part

    def _ensure_unit_group(self):
        if self.unit_group is None:
            self.unit_group = uuid.uuid4()
        return self.unit_group

    def same_type_items(self):
        """Other active items of the same type, largest stock first."""
        if self.unit_group is None:
            return type(self).objects.none()
        return (
            type(self)
            .objects.filter(unit_group=self.unit_group, is_active=True)
            .exclude(pk=self.pk)
            .order_by("-quantity", "pk")
        )

    @transaction.atomic
    def link_same_type(self, other):
        """Put this item and `other` (with their existing groups) into one group."""
        if other.pk == self.pk:
            raise ValidationError("Choose a different item.")
        group = other.unit_group or self.unit_group or uuid.uuid4()
        old_groups = {g for g in (self.unit_group, other.unit_group) if g and g != group}
        items = type(self).objects
        if old_groups:
            items.filter(unit_group__in=old_groups).update(unit_group=group)
        items.filter(pk__in=[self.pk, other.pk]).update(unit_group=group)
        self.unit_group = other.unit_group = group

    @transaction.atomic
    def unlink_same_type(self):
        group = self.unit_group
        if group is None:
            return
        self.unit_group = None
        self.save(update_fields=["unit_group"])
        rest = type(self).objects.filter(unit_group=group)
        if rest.count() == 1:
            rest.update(unit_group=None)

    @transaction.atomic
    def merge_into(self, target, user):
        """Return all units of this item to `target` and deactivate this item."""
        if target.pk == self.pk or self.unit_group is None or target.unit_group != self.unit_group:
            raise ValidationError("Merge only into another item of the same type.")
        if not (self.is_active and target.is_active):
            raise ValidationError("Both items must be active.")
        if self.is_lent or target.is_lent:
            raise ValidationError("Return the loan before merging.")
        if self.installed_parts.filter(is_active=True).exists():
            raise ValidationError("Unmount the items mounted on this one first.")
        target.quantity += self.quantity
        target.updated_by = user
        target.save(update_fields=["quantity", "updated_by", "updated_at"])
        note = f"Merged into {target.inventory_number}."
        self.comment = f"{self.comment}\n{note}" if self.comment else note
        self.is_active = False
        self.installed_in = None
        self.updated_by = user
        self.save(
            update_fields=["comment", "is_active", "installed_in", "updated_by", "updated_at"]
        )


class Loan(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="loans")
    borrower_name = models.CharField(max_length=200)
    borrower_contact = models.CharField(max_length=200, blank=True)
    borrowed_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="loans_recorded"
    )
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-borrowed_at"]
        indexes = [models.Index(fields=["due_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=Q(returned_at__isnull=True),
                name="one_open_loan_per_item",
            ),
        ]

    def __str__(self):
        return f"{self.item} → {self.borrower_name}"

    @property
    def is_overdue(self) -> bool:
        if self.returned_at:
            return False
        return self.due_date < timezone.localdate()

    def clean(self):
        super().clean()
        reject_newlines(self.borrower_name, "Borrower name")
        reject_newlines(self.note, "Note")
        self.borrower_contact = validate_optional_email_or_text(self.borrower_contact or "")

    def return_item(self):
        self.returned_at = timezone.now()
        self.save(update_fields=["returned_at"])


class Stocktake(models.Model):
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="stocktakes"
    )
    scope_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stocktakes_scoped",
        help_text="If set, only items in this room (and its places) are expected.",
    )
    current_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stocktakes_current",
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Stocktake {self.pk}"

    @property
    def is_open(self) -> bool:
        return self.finished_at is None


class StocktakeScan(models.Model):
    stocktake = models.ForeignKey(
        Stocktake, on_delete=models.CASCADE, related_name="scans"
    )
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stocktake_scans")
    scanned_at = models.DateTimeField(default=timezone.now)
    scanned_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="stocktake_scans"
    )
    expected_location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="stocktake_expected"
    )
    found_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stocktake_found",
    )

    expected_quantity = models.PositiveIntegerField(null=True, blank=True)
    counted_quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stocktake", "item"],
                name="one_scan_per_item_per_stocktake",
            ),
        ]
        indexes = [models.Index(fields=["stocktake", "scanned_at"])]

    def __str__(self):
        return f"{self.item} in stocktake {self.stocktake_id}"

    @property
    def needs_count(self) -> bool:
        return self.counted_quantity is None and (self.expected_quantity or 0) > 1

    @property
    def quantity_differs(self) -> bool:
        return (
            self.counted_quantity is not None
            and self.expected_quantity is not None
            and self.counted_quantity != self.expected_quantity
        )
