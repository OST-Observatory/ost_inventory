from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def relative_due(due_date):
    if not due_date:
        return ""
    today = timezone.localdate()
    delta = (due_date - today).days
    if delta == 0:
        return "due today"
    if delta == 1:
        return "due in 1 day"
    if delta > 1:
        return f"due in {delta} days"
    overdue = abs(delta)
    if overdue == 1:
        return "overdue 1 day"
    return f"overdue {overdue} days"


@register.simple_tag(takes_context=True)
def query_without(context, *keys):
    params = context["request"].GET.copy()
    for key in keys:
        params.pop(key, None)
    params.pop("page", None)
    return params.urlencode()


@register.simple_tag(takes_context=True)
def page_query(context, page):
    params = context["request"].GET.copy()
    params["page"] = page
    return params.urlencode()


@register.simple_tag(takes_context=True)
def nav_current(context, *names):
    match = getattr(context.get("request"), "resolver_match", None)
    current = getattr(match, "url_name", "") or ""
    return "page" if current in names else ""
