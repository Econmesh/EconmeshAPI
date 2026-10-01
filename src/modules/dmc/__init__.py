"""DMC agent portfolio, queue and direct channel."""

from src.modules.dmc.admin_routes import router as admin_router
from src.modules.dmc.routes import router
from src.modules.dmc.user_routes import router as user_router

__all__ = ["admin_router", "router", "user_router"]
