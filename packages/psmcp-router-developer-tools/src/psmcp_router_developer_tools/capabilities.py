"""Request-scoped root capabilities across FastMCP's mounted child contexts."""

from contextvars import ContextVar

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from fastmcp.tools.tool import ToolResult

publication_root: ContextVar[FastMCP | None] = ContextVar("skill_publication_root", default=None)


class SkillPublicationMiddleware(Middleware):
    """Keep root identity isolated even when a child router is shared by servers."""

    async def on_call_tool(self, context: MiddlewareContext, call_next: CallNext) -> ToolResult:
        """Expose the actual root only for this tool request and reset on failure."""
        if context.fastmcp_context is None:
            return await call_next(context)
        token = publication_root.set(context.fastmcp_context.fastmcp)
        try:
            return await call_next(context)
        finally:
            publication_root.reset(token)
