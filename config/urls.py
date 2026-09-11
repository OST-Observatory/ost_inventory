from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import InventoryLoginView, InventoryLogoutView
from inventory.views import ItemDetailView, LocationDetailView
from inventory.views.media import protected_media


def build_urlpatterns(*, subpath=False):
    """URL map for a dedicated host, or for SCRIPT_NAME=/inventory (subpath).

    On a dedicated vhost PATH_INFO still contains /inventory/. Behind
    ``ProxyPass /inventory`` Apache sets SCRIPT_NAME=/inventory and PATH_INFO
    is the remainder; mounting the app at "" avoids /inventory/inventory/.
    """
    media_prefix = settings.MEDIA_URL.lstrip("/")
    common = [
        path("admin/", admin.site.urls),
        path("login/", InventoryLoginView.as_view(), name="login"),
        path("logout/", InventoryLogoutView.as_view(), name="logout"),
        path("i/<int:pk>/", ItemDetailView.as_view(), name="item_short"),
        path("l/<int:pk>/", LocationDetailView.as_view(), name="location_short"),
        path(f"{media_prefix}<path:path>", protected_media, name="protected_media"),
    ]
    if subpath:
        return [
            *common,
            path("", include("accounts.urls")),
            path("", include("inventory.urls")),
        ]
    return [
        *common,
        path("inventory/admin/", include("accounts.urls")),
        path("", RedirectView.as_view(pattern_name="inventory:search", permanent=False)),
        path("inventory/", include("inventory.urls")),
    ]


urlpatterns = build_urlpatterns(subpath=False)
