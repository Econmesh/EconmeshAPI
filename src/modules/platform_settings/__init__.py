"""Global platform settings (feature toggles)."""

from src.modules.platform_settings.admin_routes import router as admin_router
from src.modules.platform_settings.routes import router

__all__ = ["admin_router", "router"]
