"""URLConf when FORCE_SCRIPT_NAME=/inventory (Apache SCRIPT_NAME)."""
from config.urls import build_urlpatterns

urlpatterns = build_urlpatterns(subpath=True)
