"""Integration tests that require OmniFocus to be running.

Run with: pytest tests/test_integration.py
These tests talk to a live OmniFocus instance -- they will create and delete
a temporary test task to verify CRUD operations.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time

from pymnifocus.applescript_gen import gen_add_task, gen_remove_item
from pymnifocus.omnifocus import (
    execute_applescript,
    execute_omnifocus_script,
    query_omnifocus,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cli(*args: str) -> subprocess.CompletedProcess:
    """Run pymnifocus-query via the module entry point."""
    return subprocess.run(
        [sys.executable, "-m", "pymnifocus.cli", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


async def _mcp_session():
    """Spin up an MCP server subprocess and return a connected session context."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pymnifocus.server"],
    )
    read_stream, write_stream = None, None

    cm = stdio_client(params)
    transport = await cm.__aenter__()
    read_stream, write_stream = transport

    session = ClientSession(read_stream, write_stream)
    await session.__aenter__()
    await session.initialize()
    return cm, session


async def _mcp_cleanup(cm, session):
    await session.__aexit__(None, None, None)
    await cm.__aexit__(None, None, None)


# ===========================================================================
# OmniFocus connection (direct Python calls)
# ===========================================================================

class TestOmniFocusConnection:
    """Verify we can talk to OmniFocus through the Python layer."""

    def test_query_tasks(self):
        result = query_omnifocus({"entity": "tasks", "limit": 5})
        assert result["success"] is True
        assert isinstance(result.get("items"), list)

    def test_query_projects(self):
        result = query_omnifocus({"entity": "projects", "limit": 5})
        assert result["success"] is True

    def test_query_folders(self):
        result = query_omnifocus({"entity": "folders", "limit": 5})
        assert result["success"] is True

    def test_query_with_filters(self):
        result = query_omnifocus({
            "entity": "tasks",
            "filters": {"status": ["Available", "Next"]},
            "limit": 5,
        })
        assert result["success"] is True

    def test_query_summary_mode(self):
        result = query_omnifocus({"entity": "tasks", "summary": True})
        assert result["success"] is True
        assert isinstance(result["count"], int)
        assert result["count"] >= 0

    def test_list_tags(self):
        raw = execute_omnifocus_script("listTags.js")
        data = raw if isinstance(raw, dict) else json.loads(raw)
        assert "tags" in data
        assert isinstance(data["tags"], list)

    def test_list_perspectives(self):
        raw = execute_omnifocus_script("listPerspectives.js")
        data = raw if isinstance(raw, dict) else json.loads(raw)
        assert "perspectives" in data
        assert isinstance(data["perspectives"], list)


# ===========================================================================
# CRUD -- create a task, verify it, remove it
# ===========================================================================

class TestCRUD:
    """Create and remove a test task to verify write operations."""

    def test_create_and_remove_task(self, test_task_name):
        # --- create ---
        script = gen_add_task(name=test_task_name, note="pytest integration test")
        out = execute_applescript(script)
        result = json.loads(out)
        assert result["success"] is True, f"Create failed: {result}"
        task_id = result["taskId"]

        # --- verify it shows up ---
        query = query_omnifocus({
            "entity": "tasks",
            "filters": {"inbox": True},
            "limit": 200,
        })
        names = [t["name"] for t in (query.get("items") or [])]
        assert test_task_name in names, f"Task not found in inbox: {names}"

        # --- remove ---
        script = gen_remove_item(item_id=task_id, item_type="task")
        out = execute_applescript(script)
        result = json.loads(out)
        assert result["success"] is True, f"Remove failed: {result}"


# ===========================================================================
# CLI tool
# ===========================================================================

class TestCLI:
    """Test the pymnifocus-query CLI."""

    def test_help(self):
        r = _cli("--help")
        assert r.returncode == 0
        assert "Query OmniFocus" in r.stdout

    def test_overdue_json(self):
        r = _cli("--overdue", "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["success"] is True

    def test_tags(self):
        r = _cli("--tags")
        assert r.returncode == 0

    def test_perspectives(self):
        r = _cli("--perspectives")
        assert r.returncode == 0

    def test_json_input(self):
        r = _cli('{"entity": "tasks", "limit": 3}', "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["success"] is True
        assert len(data.get("items", [])) <= 3

    def test_summary(self):
        r = _cli("--available", "--summary")
        assert r.returncode == 0
        assert "Found" in r.stdout

    def test_invalid_json_rejected(self):
        r = _cli("{not valid json}")
        assert r.returncode != 0

    def test_invalid_entity_rejected(self):
        r = _cli('{"entity": "evil"}')
        assert r.returncode != 0 or "Error" in (r.stdout + r.stderr)


# ===========================================================================
# MCP server
# ===========================================================================

class TestMCPServer:
    """Test the MCP server over stdio."""

    def test_connect_and_list_tools(self):
        async def _test():
            cm, session = await _mcp_session()
            try:
                tools = await session.list_tools()
                return [t.name for t in tools.tools]
            finally:
                await _mcp_cleanup(cm, session)

        tool_names = asyncio.run(_test())
        expected = {
            "query_omnifocus", "dump_database", "add_omnifocus_task",
            "add_project", "remove_item", "edit_item",
            "batch_add_items", "batch_remove_items",
            "list_perspectives", "get_perspective_view", "list_tags",
        }
        assert expected == set(tool_names)

    def test_query_via_mcp(self):
        async def _test():
            cm, session = await _mcp_session()
            try:
                result = await session.call_tool(
                    "query_omnifocus",
                    arguments={"entity": "tasks", "limit": 3},
                )
                return result.content[0].text
            finally:
                await _mcp_cleanup(cm, session)

        text = asyncio.run(_test())
        assert "tasks" in text.lower() or "Query Results" in text

    def test_list_tags_via_mcp(self):
        async def _test():
            cm, session = await _mcp_session()
            try:
                result = await session.call_tool("list_tags")
                return result.content[0].text
            finally:
                await _mcp_cleanup(cm, session)

        text = asyncio.run(_test())
        assert "Tags" in text or "tags" in text.lower()

    def test_create_and_remove_via_mcp(self, test_task_name):
        async def _test():
            cm, session = await _mcp_session()
            try:
                create = await session.call_tool(
                    "add_omnifocus_task",
                    arguments={"name": test_task_name, "note": "MCP pytest"},
                )
                create_text = create.content[0].text
                assert "successfully" in create_text.lower()

                remove = await session.call_tool(
                    "remove_item",
                    arguments={"item_type": "task", "name": test_task_name},
                )
                remove_text = remove.content[0].text
                assert "successfully" in remove_text.lower()
            finally:
                await _mcp_cleanup(cm, session)

        asyncio.run(_test())


# ===========================================================================
# MCP server -- HTTP transport
# ===========================================================================

def _find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    """Block until a TCP connection to localhost:port succeeds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not start on port {port} within {timeout}s")


class TestMCPServerHTTP:
    """Test the MCP server over streamable-http transport."""

    def test_connect_and_list_tools_http(self):
        port = _find_free_port()

        async def _test():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "pymnifocus.server",
                    "--transport", "streamable-http",
                    "--port", str(port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                await asyncio.to_thread(_wait_for_port, port)

                url = f"http://127.0.0.1:{port}/mcp"
                async with streamablehttp_client(url) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        return [t.name for t in tools.tools]
            finally:
                proc.terminate()
                proc.wait(timeout=5)

        tool_names = asyncio.run(_test())
        expected = {
            "query_omnifocus", "dump_database", "add_omnifocus_task",
            "add_project", "remove_item", "edit_item",
            "batch_add_items", "batch_remove_items",
            "list_perspectives", "get_perspective_view", "list_tags",
        }
        assert expected == set(tool_names)

    def test_query_via_http(self):
        port = _find_free_port()

        async def _test():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "pymnifocus.server",
                    "--transport", "streamable-http",
                    "--port", str(port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                await asyncio.to_thread(_wait_for_port, port)

                url = f"http://127.0.0.1:{port}/mcp"
                async with streamablehttp_client(url) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            "query_omnifocus",
                            arguments={"entity": "tasks", "limit": 3},
                        )
                        return result.content[0].text
            finally:
                proc.terminate()
                proc.wait(timeout=5)

        text = asyncio.run(_test())
        assert "tasks" in text.lower() or "Query Results" in text

    def test_list_resources_via_http(self):
        port = _find_free_port()

        async def _test():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "pymnifocus.server",
                    "--transport", "streamable-http",
                    "--port", str(port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                await asyncio.to_thread(_wait_for_port, port)

                url = f"http://127.0.0.1:{port}/mcp"
                async with streamablehttp_client(url) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        resources = await session.list_resources()
                        return [r.uri for r in resources.resources]
            finally:
                proc.terminate()
                proc.wait(timeout=5)

        uris = asyncio.run(_test())
        uri_strings = [str(u) for u in uris]
        assert any("inbox" in u for u in uri_strings)
        assert any("today" in u for u in uri_strings)
        assert any("flagged" in u for u in uri_strings)
        assert any("stats" in u for u in uri_strings)
