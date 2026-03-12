"""CLI tool to query OmniFocus from the command line.

Accepts the same JSON format as the MCP query_omnifocus tool,
plus convenience flags for common queries.

Examples:
    omnifocus-query '{"entity": "tasks", "filters": {"flagged": true}}'
    omnifocus-query --overdue
    omnifocus-query --project "Weekly Review" --limit 10
    echo '{"entity": "tasks", "filters": {"status": ["Next"]}}' | omnifocus-query
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from pymnifocus.omnifocus import execute_omnifocus_script, query_omnifocus


def _build_query_from_flags(args: argparse.Namespace) -> dict | None:
    """Build a query dict from convenience flags. Returns None if no flags used."""
    filters: dict = {}
    has_shortcut = False

    if args.inbox:
        filters["inbox"] = True
        has_shortcut = True
    if args.flagged:
        filters["flagged"] = True
        has_shortcut = True
    if args.overdue:
        filters["status"] = filters.get("status", []) + ["Overdue"]
        has_shortcut = True
    if args.due_soon:
        filters["status"] = filters.get("status", []) + ["DueSoon"]
        has_shortcut = True
    if args.available:
        filters["status"] = filters.get("status", []) + ["Available", "Next"]
        has_shortcut = True
    if args.blocked:
        filters["status"] = filters.get("status", []) + ["Blocked"]
        has_shortcut = True
    if args.due_within is not None:
        filters["dueWithin"] = args.due_within
        has_shortcut = True
    if args.planned_within is not None:
        filters["plannedWithin"] = args.planned_within
        has_shortcut = True
    if args.project:
        filters["projectName"] = args.project
        has_shortcut = True
    if args.tag:
        filters["tags"] = args.tag
        has_shortcut = True
    if args.today:
        filters["dueOn"] = 0
        has_shortcut = True
    if args.has_note is not None:
        filters["hasNote"] = args.has_note
        has_shortcut = True

    if not has_shortcut:
        return None

    query: dict = {"entity": args.entity or "tasks", "filters": filters}
    if args.fields:
        query["fields"] = args.fields
    if args.limit:
        query["limit"] = args.limit
    if args.sort:
        query["sortBy"] = args.sort
    if args.sort_order:
        query["sortOrder"] = args.sort_order
    if args.completed:
        query["includeCompleted"] = True
    if args.summary:
        query["summary"] = True
    return query


def _format_items(items: list[dict], entity: str) -> str:
    """Format query result items for terminal display."""
    if not items:
        return "No items found."
    lines = []
    for item in items:
        if entity == "tasks":
            flag = "🚩 " if item.get("flagged") else "  "
            name = item.get("name", "Unnamed")
            status = item.get("taskStatus", "")
            proj = item.get("projectName") or ""
            due = ""
            if item.get("dueDate"):
                try:
                    dt = datetime.fromisoformat(item["dueDate"].replace("Z", "+00:00"))
                    due = dt.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    due = item["dueDate"][:10]
            tags = ", ".join(item.get("tagNames", []))

            parts = [f"{flag}{name}"]
            if status and status not in ("Available", "Next"):
                parts.append(f"[{status}]")
            if proj:
                parts.append(f"({proj})")
            if due:
                parts.append(f"due:{due}")
            if tags:
                parts.append(f"<{tags}>")
            lines.append(" ".join(parts))
        elif entity == "projects":
            status = item.get("status", "Active")
            suffix = f" [{status}]" if status != "Active" else ""
            count = item.get("taskCount")
            count_str = f" ({count} tasks)" if count is not None else ""
            lines.append(f"  {item.get('name', '')}{suffix}{count_str}")
        elif entity == "folders":
            path = item.get("path", item.get("name", ""))
            count = item.get("projectCount")
            count_str = f" ({count} projects)" if count is not None else ""
            lines.append(f"  {path}{count_str}")
        else:
            lines.append(f"  {json.dumps(item)}")
    return "\n".join(lines)


def _run_query(query: dict, output_json: bool) -> int:
    """Execute a query and print results."""
    result = query_omnifocus(query)
    if not result.get("success"):
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return 1

    if output_json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    if query.get("summary"):
        entity = query.get("entity", "items")
        print(f"Found {result.get('count', 0)} {entity}.")
        return 0

    items = result.get("items") or []
    entity = query.get("entity", "tasks")
    count = result.get("count", len(items))
    if not items:
        print(f"No {entity} found matching the specified criteria.")
        return 0
    print(f"{count} {entity} found:\n")
    print(_format_items(items, entity))
    if query.get("limit") and len(items) >= query["limit"]:
        print(f"\n(limited to {query['limit']} results)")
    return 0


def _run_tool(tool: str, output_json: bool) -> int:
    """Run a non-query tool (dump, tags, perspectives)."""
    try:
        if tool == "dump":
            raw = execute_omnifocus_script("omnifocusDump.js")
            if output_json:
                data = raw if isinstance(raw, dict) else json.loads(raw)
                print(json.dumps(data, indent=2, default=str))
            else:
                data = raw if isinstance(raw, dict) else json.loads(raw)
                tasks = data.get("tasks", [])
                projects = data.get("projects", {})
                folders = data.get("folders", {})
                tags = data.get("tags", {})
                print(f"Database snapshot ({data.get('exportDate', 'unknown')}):")
                print(f"  {len(tasks)} tasks, {len(projects)} projects, "
                      f"{len(folders)} folders, {len(tags)} tags")
                active = [t for t in tasks if t.get("taskStatus") not in ("Completed", "Dropped")]
                flagged = [t for t in active if t.get("flagged")]
                inbox = [t for t in active if t.get("inInbox")]
                print(f"  {len(active)} active, {len(flagged)} flagged, {len(inbox)} in inbox")
        elif tool == "tags":
            raw = execute_omnifocus_script("listTags.js")
            data = raw if isinstance(raw, dict) else json.loads(raw)
            if output_json:
                print(json.dumps(data, indent=2, default=str))
            else:
                tags = data.get("tags", [])
                for t in tags:
                    parent = f" (under {t['parentName']})" if t.get("parentName") else ""
                    active = "" if t.get("active", True) else " [dropped]"
                    print(f"  {t.get('name', '')}{parent}{active} — {t.get('taskCount', 0)} tasks")
        elif tool == "perspectives":
            raw = execute_omnifocus_script("listPerspectives.js")
            data = raw if isinstance(raw, dict) else json.loads(raw)
            if output_json:
                print(json.dumps(data, indent=2, default=str))
            else:
                for p in data.get("perspectives", []):
                    kind = "built-in" if p.get("isBuiltIn") else "custom"
                    print(f"  {p.get('name', '')} ({kind})")
        else:
            print(f"Unknown tool: {tool}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="omnifocus-query",
        description="Query OmniFocus from the command line",
        epilog="""examples:
  %(prog)s '{"entity": "tasks", "filters": {"flagged": true}}'
  %(prog)s '{"entity": "tasks", "filters": {"status": ["Overdue", "DueSoon"]}}'
  %(prog)s --flagged
  %(prog)s --overdue --due-soon
  %(prog)s --project "Weekly Review" --limit 10
  %(prog)s --due-within 7 --sort dueDate
  %(prog)s --today
  %(prog)s --tag work --tag urgent
  %(prog)s --inbox --json
  %(prog)s --dump
  %(prog)s --tags
  %(prog)s --perspectives
  echo '{"entity": "tasks", "summary": true}' | %(prog)s""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "json_input", nargs="?", default=None,
        help="JSON query (same format as MCP query_omnifocus tool)",
    )

    shortcuts = parser.add_argument_group("query shortcuts")
    shortcuts.add_argument("--inbox", action="store_true", help="inbox tasks")
    shortcuts.add_argument("--flagged", action="store_true", help="flagged tasks")
    shortcuts.add_argument("--overdue", action="store_true", help="overdue tasks")
    shortcuts.add_argument("--due-soon", action="store_true", help="tasks due soon")
    shortcuts.add_argument("--available", action="store_true", help="available/next tasks")
    shortcuts.add_argument("--blocked", action="store_true", help="blocked tasks")
    shortcuts.add_argument("--today", action="store_true", help="tasks due today")
    shortcuts.add_argument("--due-within", type=int, metavar="DAYS", help="tasks due within N days")
    shortcuts.add_argument("--planned-within", type=int, metavar="DAYS", help="tasks planned within N days")
    shortcuts.add_argument("--project", "-p", metavar="NAME", help="tasks in project (partial match)")
    shortcuts.add_argument("--tag", "-t", action="append", metavar="TAG", help="tasks with tag (repeatable)")
    shortcuts.add_argument("--has-note", action="store_true", default=None, dest="has_note", help="tasks that have notes")
    shortcuts.add_argument("--no-note", action="store_false", dest="has_note", help="tasks without notes")

    query_opts = parser.add_argument_group("query options")
    query_opts.add_argument("--entity", "-e", default=None, help="entity type: tasks, projects, folders (default: tasks)")
    query_opts.add_argument("--fields", "-f", nargs="+", metavar="FIELD", help="fields to return")
    query_opts.add_argument("--limit", "-n", type=int, help="max results")
    query_opts.add_argument("--sort", "-s", metavar="FIELD", help="sort by field (e.g. dueDate, name)")
    query_opts.add_argument("--sort-order", choices=["asc", "desc"], default=None, help="sort direction")
    query_opts.add_argument("--completed", action="store_true", help="include completed items")
    query_opts.add_argument("--summary", action="store_true", help="return count only")

    tools = parser.add_argument_group("other tools")
    tools.add_argument("--dump", action="store_true", help="full database dump")
    tools.add_argument("--tags", action="store_true", help="list all tags")
    tools.add_argument("--perspectives", action="store_true", help="list all perspectives")

    output = parser.add_argument_group("output")
    output.add_argument("--json", action="store_true", dest="output_json", help="output raw JSON")

    args = parser.parse_args()

    # Handle non-query tools
    if args.dump:
        sys.exit(_run_tool("dump", args.output_json))
    if args.tags:
        sys.exit(_run_tool("tags", args.output_json))
    if args.perspectives:
        sys.exit(_run_tool("perspectives", args.output_json))

    # Build query from shortcut flags
    query = _build_query_from_flags(args)

    # Or from JSON input (positional arg or stdin)
    if query is None:
        json_str = args.json_input
        if json_str is None and not sys.stdin.isatty():
            json_str = sys.stdin.read().strip()
        if not json_str:
            parser.print_help()
            sys.exit(0)
        try:
            query = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(query, dict) or "entity" not in query:
            print('JSON must be an object with at least an "entity" field.', file=sys.stderr)
            sys.exit(1)

    # Apply CLI overrides to JSON queries too
    if args.limit and "limit" not in query:
        query["limit"] = args.limit
    if args.sort and "sortBy" not in query:
        query["sortBy"] = args.sort
    if args.sort_order and "sortOrder" not in query:
        query["sortOrder"] = args.sort_order
    if args.completed and not query.get("includeCompleted"):
        query["includeCompleted"] = True
    if args.summary and not query.get("summary"):
        query["summary"] = True
    if args.fields and "fields" not in query:
        query["fields"] = args.fields

    sys.exit(_run_query(query, args.output_json))


if __name__ == "__main__":
    main()
