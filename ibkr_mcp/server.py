import secrets
from os import getenv
from typing import Any

from fastmcp import FastMCP

from ibkr_mcp.ibkr.client import IBKRClient
from ibkr_mcp.ibkr.types import Position

mcp: FastMCP = FastMCP(name="IBKR MCP Server", version="0.1.0")

ibkr_client = IBKRClient()


def ensure_ibkr_connection(func):
    """Ensure the IBKR client is connected before executing a function."""

    def wrapper_func() -> Any:
        """Get the IBKR client connection details and connect if not already connected."""
        host = getenv("IBKR_HOST", "localhost")
        port = int(getenv("IBKR_PORT", "4001"))
        client_id = int(getenv("IBKR_CLIENT_ID", secrets.randbelow(999_999)))

        if not ibkr_client.is_connected():
            ibkr_client.connect(host=host, port=port, client_id=client_id)

        return func()

    return wrapper_func


@ensure_ibkr_connection
async def _get_positions_from_ibkr() -> frozenset[Position]:
    """Get positions from the IBKR client."""
    return await ibkr_client.get_positions()


@mcp.tool(description="Get current positions from IBKR")
async def get_positions() -> list[dict[str, Any]]:
    """Get current positions."""
    return [
        position.model_dump()
        for position in await _get_positions_from_ibkr()
    ]


if __name__ == "__main__":
    mcp.run()
