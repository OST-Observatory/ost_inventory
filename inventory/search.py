from django.db import connection
from django.db.models import Exists, OuterRef, Q


def _inventory_number_q(q):
    """Match #{pk} / #0042 / 42. The number is derived from pk, not a column."""
    text = (q or "").strip()
    if text.startswith("#"):
        text = text[1:].strip()
    if not text.isdigit():
        return Q()
    return Q(pk=int(text))


def _related_text_q(q):
    """Match related rows without joining them into the item queryset."""
    from inventory.models import Category, Item, Project

    return (
        Exists(Category.objects.filter(items=OuterRef("pk"), name__icontains=q))
        | Exists(Project.objects.filter(pk=OuterRef("project_id"), name__icontains=q))
        | Exists(Item.objects.filter(pk=OuterRef("installed_in_id"), name__icontains=q))
    )


def filter_items(
    queryset,
    *,
    q="",
    category="",
    location="",
    project="",
    container="",
    on_loan=False,
    include_inactive=False,
):
    """Filter items for search UI. SQLite: icontains; PostgreSQL: full-text + trigram."""
    from inventory.models import Category, Loan, Location

    if not include_inactive:
        queryset = queryset.filter(is_active=True)

    q = (q or "").strip()
    if q:
        related = _related_text_q(q)
        by_number = _inventory_number_q(q)
        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import (
                SearchQuery,
                SearchRank,
                SearchVector,
                TrigramSimilarity,
            )

            # Only columns on Item: joining categories/project in SearchVector
            # yields one row per match and DISTINCT cannot collapse them because
            # rank/similarity differ per row.
            vector = (
                SearchVector("name", weight="A")
                + SearchVector("description", weight="B")
                + SearchVector("comment", weight="C")
                + SearchVector("container", weight="B")
            )
            query = SearchQuery(q)
            queryset = (
                queryset.annotate(
                    search=vector,
                    rank=SearchRank(vector, query),
                    sim=TrigramSimilarity("name", q),
                )
                .filter(
                    Q(search=query)
                    | Q(sim__gt=0.2)
                    | Q(name__icontains=q)
                    | Q(description__icontains=q)
                    | Q(comment__icontains=q)
                    | Q(container__icontains=q)
                    | related
                    | by_number
                )
                .order_by("-rank", "-sim", "name", "pk")
            )
        else:
            queryset = queryset.filter(
                Q(name__icontains=q)
                | Q(description__icontains=q)
                | Q(comment__icontains=q)
                | Q(container__icontains=q)
                | related
                | by_number
            ).order_by("name", "pk")

    if category:
        queryset = queryset.filter(
            Exists(Category.objects.filter(pk=category, items=OuterRef("pk")))
        )

    if location:
        try:
            loc = Location.objects.get(pk=location)
        except (Location.DoesNotExist, ValueError, TypeError):
            pass
        else:
            queryset = queryset.filter(location_id__in=loc.get_descendant_ids())

    if project:
        queryset = queryset.filter(project_id=project)

    if container:
        queryset = queryset.filter(container=container)

    if on_loan:
        queryset = queryset.filter(
            Exists(Loan.objects.filter(item_id=OuterRef("pk"), returned_at__isnull=True))
        )

    return queryset
