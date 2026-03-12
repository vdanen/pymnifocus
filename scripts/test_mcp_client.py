#!/usr/bin/env python3
"""
Test the OmniFocus MCP server by connecting as a proper MCP client.
Run from project root: uv run python scripts/test_mcp_client.py
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    project_root = Path(__file__).parent.parent
    python_path = project_root / ".venv" / "bin" / "python"

    server_params = StdioServerParameters(
        command=str(python_path),
        args=["-m", "pymnifocus.server"],
        cwd=str(project_root),
    )

    print("Connecting to OmniFocus MCP server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected!\n")

            # List available tools
            tools = await session.list_tools()
            print(f"Available tools ({len(tools.tools)}):")
            for tool in tools.tools:
                print(f"  - {tool.name}")
            print()

            # Query for overdue and due-soon tasks
            print("Querying for overdue and due-soon tasks...")
            result = await session.call_tool(
                "query_omnifocus",
                arguments={
                    "entity": "tasks",
                    "filters": {"status": ["Overdue", "DueSoon"]},
                    "limit": 20,
                },
            )
            for part in result.content:
                if hasattr(part, "text"):
                    print(part.text)
            print()

            # List tags
            print("Listing tags...")
            result = await session.call_tool("list_tags")
            for part in result.content:
                if hasattr(part, "text"):
                    print(part.text)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
