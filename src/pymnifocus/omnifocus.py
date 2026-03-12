"""OmniFocus integration via JXA (JavaScript for Automation) and AppleScript."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent / "scripts"
MAX_BUFFER = 10 * 1024 * 1024  # 10MB for large databases


def _escape_script(content: str) -> str:
    """Escape content for embedding in JXA template."""
    return content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")


def _escape_quoted(s: str) -> str:
    """Escape string for use in quoted JavaScript."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def execute_omnifocus_script(
    script_path_or_name: str, args: list[str] | None = None
) -> str | dict:
    """
    Execute an OmniJS script inside OmniFocus via evaluateJavascript.
    Scripts run in OmniFocus context with access to flattenedTasks, flattenedProjects, etc.
    Accepts script name (e.g. 'omnifocusDump.js') or absolute path to a script file.
    """
    if os.path.isabs(script_path_or_name) and os.path.isfile(script_path_or_name):
        script_content = Path(script_path_or_name).read_text(encoding="utf-8")
    else:
        script_path = (SCRIPT_DIR / script_path_or_name).resolve()
        if not script_path.is_relative_to(SCRIPT_DIR.resolve()):
            raise ValueError(f"Script path escapes scripts directory: {script_path_or_name}")
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        script_content = script_path.read_text(encoding="utf-8")

    if args:
        escaped_args = ", ".join(f'"{_escape_quoted(str(a))}"' for a in args)
        wrapped = f"const argv = [{escaped_args}];\n\n{script_content}"
    else:
        wrapped = script_content

    escaped_script = _escape_script(wrapped)
    jxa_wrapper = f'''function run() {{
  try {{
    const app = Application('OmniFocus');
    app.includeStandardAdditions = true;
    const result = app.evaluateJavascript(`{escaped_script}`);
    return result;
  }} catch (e) {{
    return JSON.stringify({{ error: e.message }});
  }}
}}
'''

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(jxa_wrapper)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", temp_path],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
    finally:
        os.unlink(temp_path)

    stdout = result.stdout or ""
    if result.returncode != 0:
        raise RuntimeError(f"Script failed: {result.stderr or stdout}")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return stdout


def query_omnifocus(params: dict) -> dict:
    """Execute a query against OmniFocus. Returns {success, items?, count?, error?}."""
    from .query_generator import generate_query_script

    script = generate_query_script(
        entity=params["entity"],
        filters=params.get("filters"),
        fields=params.get("fields"),
        limit=params.get("limit"),
        sort_by=params.get("sortBy"),
        sort_order=params.get("sortOrder") or "asc",
        include_completed=params.get("includeCompleted", False),
        summary=params.get("summary", False),
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        temp_path = f.name
    try:
        result = execute_omnifocus_script(temp_path)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                return {"success": False, "error": f"Invalid response: {result[:500]}"}
        if isinstance(result, dict) and result.get("error"):
            return {"success": False, "error": result["error"]}
        if not isinstance(result, dict):
            return {"success": False, "error": f"Unexpected result type: {type(result).__name__}"}
        return {
            "success": True,
            "items": result.get("items"),
            "count": result.get("count", 0),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def execute_applescript(script: str) -> str:
    """Execute raw AppleScript via osascript."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".applescript", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["osascript", temp_path],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
    finally:
        os.unlink(temp_path)

    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def execute_jxa_script(script_content: str) -> dict | list:
    """Execute raw JXA script (runs outside OmniFocus - no OmniJS globals)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(script_content)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", temp_path],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
    finally:
        os.unlink(temp_path)

    stdout = result.stdout or ""
    if result.returncode != 0:
        raise RuntimeError(f"JXA failed: {result.stderr or stdout}")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": stdout, "raw": True}
