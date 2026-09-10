from collections import deque

from django.core.exceptions import ValidationError
from django.db import models
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
        help_text="Another inventory item this one is built into.",
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
                {"installed_in": "An item cannot be installed in itself."}
            )
        host_id = self.installed_in_id
        seen = {self.pk} if self.pk else set()
        while host_id:
            if host_id in seen:
                raise ValidationError(
                    {"installed_in": "That would create a loop of installed items."}
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
