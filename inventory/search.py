from django.db import connection
from django.db.models import Q


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
    if not include_inactive:
        queryset = queryset.filter(is_active=True)

    q = (q or "").strip()
    if q:
        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import (
                SearchQuery,
                SearchRank,
                SearchVector,
                TrigramSimilarity,
            )

            vector = (
                SearchVector("name", weight="A")
                + SearchVector("description", weight="B")
                + SearchVector("comment", weight="C")
                + SearchVector("categories__name", weight="B")
                + SearchVector("project__name", weight="B")
                + SearchVector("container", weight="B")
                + SearchVector("installed_in__name", weight="B")
            )
            query = SearchQuery(q)
            queryset = (
                queryset.annotate(
                    search=vector,
                    rank=SearchRank(vector, query),
                    sim=TrigramSimilarity("name", q),
                )
                .filter(Q(search=query) | Q(sim__gt=0.2) | Q(name__icontains=q))
                .order_by("-rank", "-sim", "name")
            )
        else:
            queryset = queryset.filter(
                Q(name__icontains=q)
                | Q(description__icontains=q)
                | Q(comment__icontains=q)
                | Q(categories__name__icontains=q)
                | Q(project__name__icontains=q)
                | Q(container__icontains=q)
                | Q(installed_in__name__icontains=q)
            )

    if category:
        queryset = queryset.filter(categories__pk=category)

    if location:
        from .models import Location

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
        queryset = queryset.filter(loans__returned_at__isnull=True)

    return queryset.distinct()
