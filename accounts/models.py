from django.contrib.auth.models import AbstractUser, Group
from django.db import models

from .acl import ROLE_GROUPS


class User(AbstractUser):
    is_student = models.BooleanField(default=False)
    is_supervisor = models.BooleanField(default=False)

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk:
            sync_role_groups(self)


class GroupCapability(models.Model):
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="inventory_capabilities"
    )
    capability = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "capability"],
                name="accounts_groupcapability_unique",
            )
        ]
        indexes = [models.Index(fields=["capability"])]

    def __str__(self):
        return f"{self.group.name}:{self.capability}"


def sync_role_groups(user):
    """Mirror role flags onto Django groups staff/supervisor/student."""

    def _ensure_group(name: str, enabled: bool):
        grp, _ = Group.objects.get_or_create(name=name)
        if enabled:
            user.groups.add(grp)
        else:
            user.groups.remove(grp)

    _ensure_group("staff", bool(user.is_staff))
    _ensure_group("supervisor", bool(getattr(user, "is_supervisor", False)))
    _ensure_group("student", bool(getattr(user, "is_student", False)))


def is_protected_group(group) -> bool:
    return group.name in ROLE_GROUPS
