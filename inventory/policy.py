"""Role-aware queryset helpers."""
from accounts.permissions import user_can_see_inactive


def visible_items(user, queryset):
    """Readers only see active items; writers may include inactive ones."""
    if user_can_see_inactive(user):
        return queryset
    return queryset.filter(is_active=True)
