from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import InventoryLoginView, InventoryLogoutView
from inventory.views import ItemDetailView, LocationDetailView
from inventory.views.media import protected_media

_media_prefix = settings.MEDIA_URL.lstrip("/")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", InventoryLoginView.as_view(), name="login"),
    path("logout/", InventoryLogoutView.as_view(), name="logout"),
    path("inventory/admin/", include("accounts.urls")),
    path("", RedirectView.as_view(pattern_name="inventory:search", permanent=False)),
    path("inventory/", include("inventory.urls")),
    # Stable short URLs for QR labels — never change these paths
    path("i/<int:pk>/", ItemDetailView.as_view(), name="item_short"),
    path("l/<int:pk>/", LocationDetailView.as_view(), name="location_short"),
    path(f"{_media_prefix}<path:path>", protected_media, name="protected_media"),
]
