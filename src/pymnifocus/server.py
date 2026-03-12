"""OmniFocus MCP Server - Tools and resources for AI assistant integration."""

from __future__ import annotations

import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from . import omnifocus
from . import applescript_gen as asp

INSTRUCTIONS = """OmniFocus MCP server for macOS task management.

TOOL GUIDANCE:
- Prefer query_omnifocus over dump_database for targeted lookups (85-95% context savings)
- Use the "fields" parameter to request only needed fields
- Use "summary: true" for quick counts without full data
- For batch operations, prefer batch_add_items/batch_remove_items over repeated single calls

RESOURCES:
- omnifocus://inbox — current inbox items
- omnifocus://today — today's agenda (due, planned, overdue)
- omnifocus://flagged — all flagged items
- omnifocus://stats — quick database statistics
- omnifocus://project/{name} — tasks in a specific project
- omnifocus://perspective/{name} — items in a named perspective

QUERY FILTER TIPS:
- Tags filter is case-sensitive and exact match
- projectName filter is case-insensitive partial match
- Status values for tasks: Next, Available, Blocked, DueSoon, Overdue
- Status values for projects: Active, OnHold, Done, Dropped
- Combine filters with AND logic; within arrays, OR logic applies"""

mcp = FastMCP(
    "OmniFocus MCP",
    instructions=INSTRUCTIONS,
    json_response=True,
)


# ---------- Dump Database ----------
@mcp.tool()
def dump_database(
    hide_completed: bool = True,
    hide_recurring_duplicates: bool = True,
) -> str:
    """Get the complete current state of your OmniFocus database. Best for comprehensive analysis."""
    try:
        raw = omnifocus.execute_omnifocus_script("omnifocusDump.js")
        if isinstance(raw, dict) and raw.get("error"):
            return f"Error: {raw['error']}"
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        return _format_dump_report(data, hide_completed)
    except Exception as e:
        return f"Error generating report: {e}. Ensure OmniFocus is running."


def _format_dump_report(data: dict, hide_completed: bool) -> str:
    """Format dump data as compact hierarchical report."""
    today = datetime.now().strftime("%Y-%m-%d")
    out = [f"# OMNIFOCUS [{today}]", "", "F: Folder | P: Project | •: Task | 🚩: Flagged", ""]
    all_tasks = data.get("tasks", [])
    tasks_by_id = {t["id"]: t for t in all_tasks}
    projects = data.get("projects", {})
    folders = data.get("folders", {})

    def format_task(task: dict, indent: int = 2) -> list[str]:
        if hide_completed and task.get("taskStatus") in ("Completed", "Dropped"):
            return []
        flag = "🚩 " if task.get("flagged") else ""
        status = f" [{task.get('taskStatus', '')}]" if task.get("taskStatus") in ("DueSoon", "Overdue", "Blocked") else ""
        due = f" (due: {task['dueDate'][:10]})" if task.get("dueDate") else ""
        prefix = " " * indent + "• "
        lines = [f"{prefix}{flag}{task.get('name', '')}{status}{due}"]
        for child_id in task.get("children", []):
            child = tasks_by_id.get(child_id)
            if child:
                lines.extend(format_task(child, indent + 2))
        return lines

    def format_project(proj: dict, indent: int = 2) -> list[str]:
        status = proj.get("status", "Active")
        if hide_completed and status in ("Done", "Dropped"):
            return []
        status_str = f" [{status}]" if status != "Active" else ""
        lines = [f"{' ' * indent}P: {proj.get('name', '')}{status_str}"]
        proj_task_ids = proj.get("tasks", [])
        root_tasks = [
            tasks_by_id[tid] for tid in proj_task_ids
            if tid in tasks_by_id and not tasks_by_id[tid].get("parentTaskID")
        ]
        for task in root_tasks:
            lines.extend(format_task(task, indent + 2))
        return lines

    def format_folder(folder: dict, indent: int = 0) -> list[str]:
        lines = [f"{' ' * indent}F: {folder.get('name', '')}"]
        for subfolder_id in folder.get("subfolders", []):
            subfolder = folders.get(subfolder_id)
            if subfolder:
                lines.extend(format_folder(subfolder, indent + 2))
        for proj_id in folder.get("projects", []):
            proj = projects.get(proj_id)
            if proj:
                lines.extend(format_project(proj, indent + 2))
        return lines

    inbox_tasks = [t for t in all_tasks if t.get("inInbox")]
    if inbox_tasks:
        out.append("P: Inbox")
        for t in inbox_tasks:
            out.extend(format_task(t, 2))
        out.append("")

    root_folders = [f for f in folders.values() if not f.get("parentFolderID")]
    for folder in root_folders:
        out.extend(format_folder(folder))
        out.append("")

    orphan_projects = {
        pid: p for pid, p in projects.items()
        if not p.get("folderID")
    }
    for proj in orphan_projects.values():
        out.extend(format_project(proj, 0))
        out.append("")

    return "\n".join(out).rstrip()


# ---------- Query OmniFocus ----------
@mcp.tool()
def query_omnifocus(
    entity: str,
    filters: dict | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    include_completed: bool = False,
    summary: bool = False,
) -> str:
    """Efficiently query OmniFocus database with filters. Get specific tasks, projects, or folders."""
    result = omnifocus.query_omnifocus({
        "entity": entity,
        "filters": filters,
        "fields": fields,
        "limit": limit,
        "sortBy": sort_by,
        "sortOrder": sort_order,
        "includeCompleted": include_completed,
        "summary": summary,
    })
    if not result.get("success"):
        return f"Query failed: {result.get('error', 'Unknown error')}"
    if summary:
        return f"Found {result.get('count', 0)} {entity} matching your criteria."
    items = result.get("items") or []
    return _format_query_results(items, entity, filters, limit)


def _format_query_results(items: list, entity: str, filters: dict | None, limit: int | None) -> str:
    """Format query results for display."""
    if not items:
        return f"No {entity} found matching the specified criteria."
    lines = [f"## Query Results: {len(items)} {entity}", ""]
    for item in items:
        if entity == "tasks":
            flag = "🚩 " if item.get("flagged") else ""
            parts = [f"• {flag}{item.get('name', 'Unnamed')}"]
            if item.get("id"):
                parts.append(f"[{item['id']}]")
            if item.get("projectName"):
                parts.append(f"({item['projectName']})")
            if item.get("dueDate"):
                parts.append(f"[due: {item['dueDate'][:10]}]")
            if item.get("tagNames"):
                parts.append(f"<{','.join(item['tagNames'])}>")
            lines.append(" ".join(parts))
        elif entity == "projects":
            status = f" [{item.get('status', '')}]" if item.get("status") != "Active" else ""
            lines.append(f"P: {item.get('name', '')}{status}")
        elif entity == "folders":
            lines.append(f"F: {item.get('name', '')}")
    if limit and len(items) >= limit:
        lines.append("")
        lines.append(f"⚠️ Results limited to {limit} items.")
    return "\n".join(lines)


# ---------- Add Task ----------
@mcp.tool()
def add_omnifocus_task(
    name: str,
    note: str | None = None,
    due_date: str | None = None,
    defer_date: str | None = None,
    planned_date: str | None = None,
    flagged: bool = False,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
    project_name: str | None = None,
    parent_task_id: str | None = None,
    parent_task_name: str | None = None,
) -> str:
    """Add a new task to OmniFocus."""
    try:
        script = asp.gen_add_task(
            name=name,
            note=note or "",
            due_date=due_date or "",
            defer_date=defer_date or "",
            planned_date=planned_date or "",
            flagged=flagged,
            estimated_minutes=estimated_minutes,
            tags=tags or [],
            project_name=project_name or "",
            parent_task_id=parent_task_id or "",
            parent_task_name=parent_task_name or "",
        )
        out = omnifocus.execute_applescript(script)
        result = json.loads(out)
        if result.get("success"):
            loc = "in inbox"
            if result.get("placement") == "project":
                loc = f'in project "{project_name}"' if project_name else "in a project"
            elif result.get("placement") == "parent":
                loc = "under the parent task"
            tag_str = f" with tags: {', '.join(tags)}" if tags else ""
            due_str = f" due {due_date}" if due_date else ""
            return f"✅ Task \"{name}\" created successfully {loc}{due_str}{tag_str}."
        return f"Failed to create task: {result.get('error', 'Unknown error')}"
    except Exception as e:
        return f"Error creating task: {e}"


# ---------- Add Project ----------
@mcp.tool()
def add_project(
    name: str,
    note: str | None = None,
    due_date: str | None = None,
    defer_date: str | None = None,
    flagged: bool = False,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
    folder_name: str | None = None,
    sequential: bool = False,
) -> str:
    """Add a new project to OmniFocus."""
    try:
        script = asp.gen_add_project(
            name=name,
            note=note or "",
            due_date=due_date or "",
            defer_date=defer_date or "",
            flagged=flagged,
            estimated_minutes=estimated_minutes,
            tags=tags or [],
            folder_name=folder_name or "",
            sequential=sequential,
        )
        out = omnifocus.execute_applescript(script)
        result = json.loads(out)
        if result.get("success"):
            loc = f'in folder "{folder_name}"' if folder_name else "at root level"
            tag_str = f" with tags: {', '.join(tags)}" if tags else ""
            return f"✅ Project \"{name}\" created successfully {loc}{tag_str}."
        return f"Failed to create project: {result.get('error', 'Unknown error')}"
    except Exception as e:
        return f"Error creating project: {e}"


# ---------- Remove Item ----------
@mcp.tool()
def remove_item(
    item_type: str,
    id: str | None = None,
    name: str | None = None,
) -> str:
    """Remove a task or project from OmniFocus. Provide either id or name."""
    if not id and not name:
        return "Either id or name must be provided."
    try:
        script = asp.gen_remove_item(
            item_id=id or "",
            name=name or "",
            item_type=item_type,
        )
        out = omnifocus.execute_applescript(script)
        result = json.loads(out)
        if result.get("success"):
            return f"✅ {item_type.title()} \"{result.get('name', '')}\" removed successfully."
        return f"Failed to remove {item_type}: {result.get('error', 'Item not found')}"
    except Exception as e:
        return f"Error removing {item_type}: {e}"


# ---------- Edit Item (simplified) ----------
@mcp.tool()
def edit_item(
    item_type: str,
    id: str | None = None,
    name: str | None = None,
    new_name: str | None = None,
    new_note: str | None = None,
    new_due_date: str | None = None,
    new_defer_date: str | None = None,
    new_planned_date: str | None = None,
    new_flagged: bool | None = None,
) -> str:
    """Edit a task or project in OmniFocus."""
    if not id and not name:
        return "Either id or name must be provided."
    try:
        script = asp.gen_edit_item(
            item_type=item_type,
            item_id=id or "",
            item_name=name or "",
            new_name=new_name,
            new_note=new_note,
            new_due_date=new_due_date,
            new_defer_date=new_defer_date,
            new_planned_date=new_planned_date,
            new_flagged=new_flagged,
        )
        out = omnifocus.execute_applescript(script)
        result = json.loads(out)
        if result.get("success"):
            return f"✅ {item_type.title()} \"{result.get('name', '')}\" updated successfully."
        return f"Failed to update {item_type}: {result.get('error', 'Unknown error')}"
    except Exception as e:
        return f"Error updating {item_type}: {e}"


MAX_BATCH_SIZE = 100


# ---------- Batch Add ----------
@mcp.tool()
def batch_add_items(items: list[dict]) -> str:
    """Add multiple tasks or projects in a single operation (max 100)."""
    if len(items) > MAX_BATCH_SIZE:
        return f"Batch too large: {len(items)} items (max {MAX_BATCH_SIZE})."
    added = 0
    errors = []
    for it in items:
        try:
            if it.get("type") == "project":
                script = asp.gen_add_project(
                    name=it.get("name", ""),
                    note=it.get("note", ""),
                    due_date=it.get("dueDate", ""),
                    defer_date=it.get("deferDate", ""),
                    flagged=it.get("flagged", False),
                    tags=it.get("tags", []),
                    folder_name=it.get("folderName", ""),
                    sequential=it.get("sequential", False),
                )
            else:
                script = asp.gen_add_task(
                    name=it.get("name", ""),
                    note=it.get("note", ""),
                    due_date=it.get("dueDate", ""),
                    defer_date=it.get("deferDate", ""),
                    planned_date=it.get("plannedDate", ""),
                    flagged=it.get("flagged", False),
                    tags=it.get("tags", []),
                    project_name=it.get("projectName", ""),
                )
            out = omnifocus.execute_applescript(script)
            result = json.loads(out)
            if result.get("success"):
                added += 1
            else:
                errors.append(result.get("error", "Unknown error"))
        except Exception as e:
            errors.append(str(e))
    if errors:
        return f"Added {added}/{len(items)} items. Errors: {'; '.join(errors[:3])}"
    return f"✅ Added {len(items)} items successfully."


# ---------- Batch Remove ----------
@mcp.tool()
def batch_remove_items(items: list[dict]) -> str:
    """Remove multiple tasks or projects in a single operation (max 100)."""
    if len(items) > MAX_BATCH_SIZE:
        return f"Batch too large: {len(items)} items (max {MAX_BATCH_SIZE})."
    removed = 0
    errors = []
    for it in items:
        try:
            script = asp.gen_remove_item(
                item_id=it.get("id", ""),
                name=it.get("name", ""),
                item_type=it.get("itemType", "task"),
            )
            out = omnifocus.execute_applescript(script)
            result = json.loads(out)
            if result.get("success"):
                removed += 1
            else:
                errors.append(result.get("error", "Unknown error"))
        except Exception as e:
            errors.append(str(e))
    if errors:
        return f"Removed {removed}/{len(items)} items. Errors: {'; '.join(errors[:3])}"
    return f"✅ Removed {len(items)} items successfully."


# ---------- List Perspectives ----------
@mcp.tool()
def list_perspectives(
    include_built_in: bool = True,
    include_custom: bool = True,
) -> str:
    """List all available perspectives in OmniFocus."""
    try:
        result = omnifocus.execute_omnifocus_script("listPerspectives.js")
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        if isinstance(result, str):
            data = json.loads(result)
        else:
            data = result
        perspectives = data.get("perspectives", [])
        lines = ["## Available Perspectives", ""]
        for p in perspectives:
            t = " (built-in)" if p.get("isBuiltIn") else " (custom)"
            lines.append(f"- {p.get('name', '')}{t}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing perspectives: {e}"


# ---------- Get Perspective View ----------
@mcp.tool()
def get_perspective_view(
    perspective_name: str,
    limit: int = 100,
    include_metadata: bool = True,
) -> str:
    """Get items visible in a specific OmniFocus perspective."""
    try:
        result = omnifocus.execute_omnifocus_script(
            "getPerspectiveView.js",
            args=[perspective_name, str(limit)],
        )
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        if isinstance(result, str):
            data = json.loads(result)
        else:
            data = result
        items = data.get("items", [])
        lines = [f"## {data.get('perspectiveName', perspective_name)} ({len(items)} items)", ""]
        for item in items:
            flag = "🚩 " if item.get("flagged") else ""
            lines.append(f"• {flag}{item.get('name', '')} ({item.get('projectName', 'Inbox')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting perspective: {e}"


# ---------- List Tags ----------
@mcp.tool()
def list_tags(include_dropped: bool = False) -> str:
    """List all tags in OmniFocus with their hierarchy."""
    try:
        result = omnifocus.execute_omnifocus_script("listTags.js")
        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        if isinstance(result, str):
            data = json.loads(result)
        else:
            data = result
        tags = data.get("tags", [])
        lines = ["## Tags", ""]
        for t in tags:
            if not include_dropped and not t.get("active", True):
                continue
            parent = f" (under {t.get('parentName', '')})" if t.get("parentTagID") else ""
            lines.append(f"- {t.get('name', '')}{parent} ({t.get('taskCount', 0)} tasks)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tags: {e}"


# ---------- Resources ----------
@mcp.resource("omnifocus://inbox")
def resource_inbox() -> str:
    """Current OmniFocus inbox items."""
    result = omnifocus.query_omnifocus(
        {"entity": "tasks", "filters": {"inbox": True}, "fields": ["id", "name", "flagged", "dueDate", "tagNames", "taskStatus"]}
    )
    data = result.get("items", []) if result.get("success") else {"error": result.get("error")}
    return json.dumps(data, indent=2)


@mcp.resource("omnifocus://today")
def resource_today() -> str:
    """Today's agenda: due today, planned today, overdue."""
    due = omnifocus.query_omnifocus({"entity": "tasks", "filters": {"dueOn": 0}})
    planned = omnifocus.query_omnifocus({"entity": "tasks", "filters": {"plannedOn": 0}})
    overdue = omnifocus.query_omnifocus({"entity": "tasks", "filters": {"status": ["Overdue"]}})
    data = {
        "dueToday": due.get("items", []) if due.get("success") else [],
        "plannedToday": planned.get("items", []) if planned.get("success") else [],
        "overdue": overdue.get("items", []) if overdue.get("success") else [],
    }
    return json.dumps(data, indent=2)


@mcp.resource("omnifocus://flagged")
def resource_flagged() -> str:
    """All flagged OmniFocus items."""
    result = omnifocus.query_omnifocus(
        {"entity": "tasks", "filters": {"flagged": True}, "fields": ["id", "name", "dueDate", "projectName", "tagNames"]}
    )
    data = result.get("items", []) if result.get("success") else {"error": result.get("error")}
    return json.dumps(data, indent=2)


@mcp.resource("omnifocus://stats")
def resource_stats() -> str:
    """Quick OmniFocus database statistics."""
    try:
        raw = omnifocus.execute_omnifocus_script("omnifocusDump.js")
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        stats = {
            "taskCount": len(data.get("tasks", [])),
            "projectCount": len(data.get("projects", {})),
            "folderCount": len(data.get("folders", {})),
            "tagCount": len(data.get("tags", {})),
            "exportDate": data.get("exportDate"),
        }
        return json.dumps(stats, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("omnifocus://project/{name}")
def resource_project(name: str) -> str:
    """Tasks in a specific OmniFocus project."""
    result = omnifocus.query_omnifocus(
        {"entity": "tasks", "filters": {"projectName": name}, "fields": ["id", "name", "flagged", "dueDate", "tagNames"]}
    )
    data = result.get("items", []) if result.get("success") else {"error": result.get("error")}
    return json.dumps(data, indent=2)


@mcp.resource("omnifocus://perspective/{name}")
def resource_perspective(name: str) -> str:
    """Items in a named OmniFocus perspective."""
    result = omnifocus.execute_omnifocus_script("getPerspectiveView.js", args=[name, "100"])
    if isinstance(result, dict) and result.get("error"):
        return json.dumps({"error": result["error"]})
    if isinstance(result, str):
        data = json.loads(result)
    else:
        data = result
    return json.dumps(data.get("items", []), indent=2)


def main() -> None:
    """Run the MCP server with stdio transport (for Cursor, Claude, etc.)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
