"""Visual signatures and rubrics bound to a user profile."""

from src.modules.visual_signatures.admin_routes import router as admin_router
from src.modules.visual_signatures.routes import router

__all__ = ["admin_router", "router"]
