"""Generate OmniJS query scripts for OmniFocus."""

from __future__ import annotations

VALID_ENTITIES = {"tasks", "projects", "folders"}

VALID_SORT_FIELDS = {
    "name", "dueDate", "deferDate", "plannedDate", "flagged",
    "estimatedMinutes", "taskStatus", "status", "modificationDate",
    "creationDate", "completionDate", "added", "modified",
}

KNOWN_FIELDS = {
    "id", "name", "flagged", "taskStatus", "status", "dueDate", "deferDate",
    "plannedDate", "tagNames", "projectName", "projectId", "parentId",
    "childIds", "folderName", "folderID", "taskCount", "tasks",
    "projectCount", "projects", "estimatedMinutes", "note",
    "modificationDate", "modified", "creationDate", "added",
    "completionDate", "inInbox", "sequential", "completedByChildren",
}

MAX_LIMIT = 5000
MAX_BATCH_SIZE = 100


def _escape_js(s: str) -> str:
    """Escape string for use in a JavaScript double-quoted string."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _validate_int(value: object, name: str) -> int:
    """Coerce value to int or raise ValueError."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer, got {type(value).__name__}: {value!r}")


def generate_query_script(
    entity: str,
    filters: dict | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    include_completed: bool = False,
    summary: bool = False,
) -> str:
    """Generate OmniJS script for querying OmniFocus."""
    if entity not in VALID_ENTITIES:
        raise ValueError(f"Invalid entity: {entity!r}. Must be one of {VALID_ENTITIES}")

    filters = filters or {}
    include_completed_js = "true" if include_completed else "false"
    summary_js = "true" if summary else "false"

    if limit is not None:
        limit = min(_validate_int(limit, "limit"), MAX_LIMIT)
    if sort_by is not None and sort_by not in VALID_SORT_FIELDS:
        raise ValueError(f"Invalid sort_by: {sort_by!r}. Must be one of {VALID_SORT_FIELDS}")
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"

    filter_conditions = _generate_filter_conditions(entity, filters)
    sort_logic = _generate_sort_logic(sort_by, sort_order) if sort_by else ""
    limit_logic = f"filtered = filtered.slice(0, {limit});" if limit else ""
    field_mapping = _generate_field_mapping(entity, fields)

    return f'''(() => {{
  try {{
    function formatDate(date) {{
      if (!date) return null;
      return date.toISOString();
    }}
    function checkDateFilter(itemDate, daysFromNow) {{
      if (!itemDate) return false;
      const futureDate = new Date();
      futureDate.setDate(futureDate.getDate() + daysFromNow);
      return itemDate <= futureDate;
    }}
    function checkSameDay(itemDate, daysFromNow) {{
      if (!itemDate) return false;
      const target = new Date();
      target.setDate(target.getDate() + daysFromNow);
      return itemDate.getFullYear() === target.getFullYear() &&
        itemDate.getMonth() === target.getMonth() &&
        itemDate.getDate() === target.getDate();
    }}
    const taskStatusMap = {{
      [Task.Status.Available]: "Available",
      [Task.Status.Blocked]: "Blocked",
      [Task.Status.Completed]: "Completed",
      [Task.Status.Dropped]: "Dropped",
      [Task.Status.DueSoon]: "DueSoon",
      [Task.Status.Next]: "Next",
      [Task.Status.Overdue]: "Overdue"
    }};
    const projectStatusMap = {{
      [Project.Status.Active]: "Active",
      [Project.Status.Done]: "Done",
      [Project.Status.Dropped]: "Dropped",
      [Project.Status.OnHold]: "OnHold"
    }};
    let items = [];
    const entityType = "{_escape_js(entity)}";
    if (entityType === "tasks") items = flattenedTasks;
    else if (entityType === "projects") items = flattenedProjects;
    else if (entityType === "folders") items = flattenedFolders;
    let filtered = items.filter(item => {{
      if (!{include_completed_js}) {{
        if (entityType === "tasks") {{
          if (item.taskStatus === Task.Status.Completed || item.taskStatus === Task.Status.Dropped) return false;
        }} else if (entityType === "projects") {{
          if (item.status === Project.Status.Done || item.status === Project.Status.Dropped) return false;
        }}
      }}
      {filter_conditions}
      return true;
    }});
    {sort_logic}
    {limit_logic}
    if ({summary_js}) {{
      return JSON.stringify({{ count: filtered.length, error: null }});
    }}
    const results = filtered.map(item => {{
      {field_mapping}
    }});
    return JSON.stringify({{ items: results, count: results.length, error: null }});
  }} catch (error) {{
    return JSON.stringify({{ error: "Script execution error: " + error.toString(), items: [], count: 0 }});
  }}
}})();'''


def _generate_filter_conditions(entity: str, filters: dict) -> str:
    """Generate JavaScript filter conditions."""
    conditions = []
    if entity == "tasks":
        if project_name := filters.get("projectName"):
            escaped = _escape_js(str(project_name).lower())
            conditions.append(f'''
      if (item.containingProject) {{
        const projectName = item.containingProject.name.toLowerCase();
        if (!projectName.includes("{escaped}")) return false;
      }} else if ("{escaped}" !== "inbox") return false;
''')
        if project_id := filters.get("projectId"):
            conditions.append(f'''
      if (!item.containingProject || item.containingProject.id.primaryKey !== "{_escape_js(str(project_id))}") return false;
''')
        if tags := filters.get("tags"):
            if not isinstance(tags, list):
                tags = [tags]
            tag_checks = " || ".join(f'item.tags.some(t => t.name === "{_escape_js(str(t))}")' for t in tags)
            conditions.append(f"if (!({tag_checks})) return false;")
        if status := filters.get("status"):
            if not isinstance(status, list):
                status = [status]
            status_checks = " || ".join(f'taskStatusMap[item.taskStatus] === "{_escape_js(str(s))}"' for s in status)
            conditions.append(f"if (!({status_checks})) return false;")
        if filters.get("flagged") is not None:
            val = "true" if filters["flagged"] else "false"
            conditions.append(f"if (item.flagged !== {val}) return false;")
        if (due_within := filters.get("dueWithin")) is not None:
            days = _validate_int(due_within, "dueWithin")
            conditions.append(f"if (!item.dueDate || !checkDateFilter(item.dueDate, {days})) return false;")
        if (planned_within := filters.get("plannedWithin")) is not None:
            days = _validate_int(planned_within, "plannedWithin")
            conditions.append(f"if (!item.plannedDate || !checkDateFilter(item.plannedDate, {days})) return false;")
        if (due_on := filters.get("dueOn")) is not None:
            days = _validate_int(due_on, "dueOn")
            conditions.append(f"if (!checkSameDay(item.dueDate, {days})) return false;")
        if (defer_on := filters.get("deferOn")) is not None:
            days = _validate_int(defer_on, "deferOn")
            conditions.append(f"if (!checkSameDay(item.deferDate, {days})) return false;")
        if (planned_on := filters.get("plannedOn")) is not None:
            days = _validate_int(planned_on, "plannedOn")
            conditions.append(f"if (!checkSameDay(item.plannedDate, {days})) return false;")
        if filters.get("hasNote") is not None:
            val = "true" if filters["hasNote"] else "false"
            conditions.append(f'''
      const hasNote = item.note && item.note.trim().length > 0;
      if (hasNote !== {val}) return false;
''')
        if filters.get("inbox") is not None:
            if filters["inbox"]:
                conditions.append("if (!item.inInbox) return false;")
            else:
                conditions.append("if (item.inInbox) return false;")
    elif entity == "projects":
        if folder_id := filters.get("folderId"):
            conditions.append(f'''
      if (!item.parentFolder || item.parentFolder.id.primaryKey !== "{_escape_js(str(folder_id))}") return false;
''')
        if status := filters.get("status"):
            if not isinstance(status, list):
                status = [status]
            status_checks = " || ".join(f'projectStatusMap[item.status] === "{_escape_js(str(s))}"' for s in status)
            conditions.append(f"if (!({status_checks})) return false;")
    return "\n".join(conditions) if conditions else ""


def _generate_sort_logic(sort_by: str, sort_order: str) -> str:
    """Generate JavaScript sort logic. sort_by must be pre-validated."""
    order = -1 if sort_order == "desc" else 1
    prop = "taskStatus" if sort_by == "taskStatus" else sort_by
    return f'''
    filtered.sort((a, b) => {{
      let aVal = a.{prop};
      let bVal = b.{prop};
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === 'string') return aVal.localeCompare(bVal) * {order};
      if (aVal instanceof Date) return (aVal.getTime() - bVal.getTime()) * {order};
      return (aVal - bVal) * {order};
    }});
'''


def _generate_field_mapping(entity: str, fields: list[str] | None) -> str:
    """Generate JavaScript field mapping for result objects."""
    if not fields or len(fields) == 0:
        if entity == "tasks":
            return """const obj = {
        id: item.id.primaryKey,
        name: item.name || "",
        flagged: item.flagged || false,
        taskStatus: taskStatusMap[item.taskStatus] || "Unknown",
        dueDate: formatDate(item.dueDate),
        deferDate: formatDate(item.deferDate),
        plannedDate: formatDate(item.plannedDate),
        tagNames: item.tags ? item.tags.map(t => t.name) : [],
        projectName: item.containingProject ? item.containingProject.name : (item.inInbox ? "Inbox" : null),
        estimatedMinutes: item.estimatedMinutes || null,
        note: item.note || ""
      };
      return obj;"""
        if entity == "projects":
            return """const taskArray = item.tasks || [];
      return {
        id: item.id.primaryKey,
        name: item.name || "",
        status: projectStatusMap[item.status] || "Unknown",
        folderName: item.parentFolder ? item.parentFolder.name : null,
        taskCount: taskArray.length,
        flagged: item.flagged || false,
        dueDate: formatDate(item.dueDate),
        deferDate: formatDate(item.deferDate),
        note: item.note || ""
      };"""
        if entity == "folders":
            return """const projectArray = item.projects || [];
      return {
        id: item.id.primaryKey,
        name: item.name || "",
        projectCount: projectArray.length,
        path: item.container ? item.container.name + "/" + item.name : item.name
      };"""

    field_mappings = {
        "id": "id: item.id.primaryKey",
        "name": 'name: item.name || ""',
        "taskStatus": "taskStatus: taskStatusMap[item.taskStatus]",
        "status": "status: projectStatusMap[item.status]",
        "modificationDate": "modificationDate: formatDate(item.modified)",
        "modified": "modificationDate: formatDate(item.modified)",
        "creationDate": "creationDate: formatDate(item.added)",
        "added": "creationDate: formatDate(item.added)",
        "completionDate": "completionDate: item.completionDate ? formatDate(item.completionDate) : null",
        "dueDate": "dueDate: formatDate(item.dueDate)",
        "deferDate": "deferDate: formatDate(item.deferDate)",
        "plannedDate": "plannedDate: formatDate(item.plannedDate)",
        "tagNames": "tagNames: item.tags ? item.tags.map(t => t.name) : []",
        "projectName": "projectName: item.containingProject ? item.containingProject.name : (item.inInbox ? 'Inbox' : null)",
        "projectId": "projectId: item.containingProject ? item.containingProject.id.primaryKey : null",
        "parentId": "parentId: item.parent ? item.parent.id.primaryKey : null",
        "childIds": "childIds: item.children ? item.children.map(c => c.id.primaryKey) : []",
        "folderName": "folderName: item.parentFolder ? item.parentFolder.name : null",
        "folderID": "folderID: item.parentFolder ? item.parentFolder.id.primaryKey : null",
        "taskCount": "taskCount: item.tasks ? item.tasks.length : 0",
        "tasks": "tasks: item.tasks ? item.tasks.map(t => t.id.primaryKey) : []",
        "projectCount": "projectCount: item.projects ? item.projects.length : 0",
        "projects": "projects: item.projects ? item.projects.map(p => p.id.primaryKey) : []",
        "flagged": "flagged: item.flagged || false",
        "estimatedMinutes": "estimatedMinutes: item.estimatedMinutes || null",
        "note": 'note: item.note || ""',
        "inInbox": "inInbox: item.inInbox || false",
        "sequential": "sequential: item.sequential || false",
        "completedByChildren": "completedByChildren: item.completedByChildren || false",
    }

    result_fields = []
    for field in fields:
        if field in field_mappings:
            result_fields.append(field_mappings[field])
        elif field in KNOWN_FIELDS:
            result_fields.append(f"{field}: item.{field} !== undefined ? item.{field} : null")
        else:
            raise ValueError(f"Unknown field: {field!r}. Known fields: {sorted(KNOWN_FIELDS)}")

    mappings_str = ",\n        ".join(result_fields)
    return f"return {{\n        {mappings_str}\n      }};"
