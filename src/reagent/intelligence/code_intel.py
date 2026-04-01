import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

_gitnexus_available: bool | None = None


def _check_gitnexus() -> bool:
    """Check if GitNexus is available (npx gitnexus).

    Returns:
        True if GitNexus MCP server can be launched.
    """
    global _gitnexus_available
    if _gitnexus_available is not None:
        return _gitnexus_available

    _gitnexus_available = shutil.which("npx") is not None
    return _gitnexus_available


async def query_code_graph(
    repo_path: str,
    query: str,
) -> dict[str, Any] | None:
    """Query GitNexus MCP server for code intelligence.

    Returns None if GitNexus is not installed or mcp is not available.

    Args:
        repo_path: Path to the repository.
        query: Search query for code graph.

    Returns:
        Query results dict, or None if unavailable.
    """
    if not _check_gitnexus():
        return None

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        return None

    params = StdioServerParameters(
        command="npx",
        args=["-y", "gitnexus@latest", "mcp"],
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "query",
                    {"query": query, "repo": repo_path},
                )
                return {"content": result} if result else None
    except (OSError, ValueError) as exc:
        logger.debug("GitNexus query_code_graph failed: %s", exc)
        return None


async def get_symbol_context(
    repo_path: str,
    symbol: str,
) -> dict[str, Any] | None:
    """Get 360-degree view of a symbol: callers, callees, processes.

    Args:
        repo_path: Path to the repository.
        symbol: Symbol name to look up.

    Returns:
        Symbol context dict, or None if unavailable.
    """
    if not _check_gitnexus():
        return None

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        return None

    params = StdioServerParameters(
        command="npx",
        args=["-y", "gitnexus@latest", "mcp"],
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "context",
                    {"symbol": symbol, "repo": repo_path},
                )
                return {"content": result} if result else None
    except (OSError, ValueError) as exc:
        logger.debug("GitNexus get_symbol_context failed: %s", exc)
        return None


async def get_impact(
    repo_path: str,
    target: str,
    direction: str = "upstream",
) -> dict[str, Any] | None:
    """Get blast radius for a symbol.

    Args:
        repo_path: Path to the repository.
        target: Target symbol or file.
        direction: "upstream" or "downstream".

    Returns:
        Impact analysis dict, or None if unavailable.
    """
    if not _check_gitnexus():
        return None

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        return None

    params = StdioServerParameters(
        command="npx",
        args=["-y", "gitnexus@latest", "mcp"],
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "impact",
                    {
                        "target": target,
                        "repo": repo_path,
                        "direction": direction,
                    },
                )
                return {"content": result} if result else None
    except (OSError, ValueError) as exc:
        logger.debug("GitNexus get_impact failed: %s", exc)
        return None


def is_available() -> bool:
    """Synchronous check if GitNexus is available.

    Returns:
        True if GitNexus can be launched.
    """
    return shutil.which("npx") is not None
