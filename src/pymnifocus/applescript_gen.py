"""AppleScript generation for OmniFocus add/edit/remove operations."""

from __future__ import annotations

import random
from datetime import datetime


def _sanitize(s: str) -> str:
    """Escape a string for safe embedding in AppleScript double-quoted strings."""
    if not s:
        return ""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return s


def _date_var(iso_date: str) -> tuple[str, str]:
    """Create AppleScript date construction. Returns (var_name, pre_script)."""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Invalid date string: {iso_date}")
    var_name = f"dateVar{random.getrandbits(32):08x}"[:17]
    script = f"""copy current date to {var_name}
set year of {var_name} to {dt.year}
set month of {var_name} to {dt.month}
set day of {var_name} to {dt.day}
set hours of {var_name} to {dt.hour}
set minutes of {var_name} to {dt.minute}
set seconds of {var_name} to {dt.second}"""
    return var_name, script


def gen_add_task(
    name: str,
    note: str = "",
    due_date: str = "",
    defer_date: str = "",
    planned_date: str = "",
    flagged: bool = False,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
    project_name: str = "",
    parent_task_id: str = "",
    parent_task_name: str = "",
) -> str:
    """Generate AppleScript to add a task to OmniFocus."""
    name = _sanitize(name)
    note = _sanitize(note)
    project_name = _sanitize(project_name)
    parent_task_id = _sanitize(parent_task_id)
    parent_task_name = _sanitize(parent_task_name)
    tags = tags or []

    date_pre = []
    due_var = defer_var = planned_var = ""
    if due_date:
        due_var, s = _date_var(due_date)
        date_pre.append(s)
    if defer_date:
        defer_var, s = _date_var(defer_date)
        date_pre.append(s)
    if planned_date:
        planned_var, s = _date_var(planned_date)
        date_pre.append(s)

    date_pre_script = "\n\n".join(date_pre) + "\n\n" if date_pre else ""

    tag_script = ""
    for tag in tags:
        t = _sanitize(tag)
        tag_script += f'''
 try
  set theTag to first flattened tag where name = "{t}"
  add theTag to tags of newTask
 on error
  try
   set theTag to make new tag with properties {{name:"{t}"}}
   add theTag to tags of newTask
  on error
  end try
 end try'''

    note_line = f'set note of newTask to "{note}"' if note else ""
    due_line = f"set due date of newTask to {due_var}" if due_var else ""
    defer_line = f"set defer date of newTask to {defer_var}" if defer_var else ""
    planned_line = f"set planned date of newTask to {planned_var}" if planned_var else ""
    flag_line = "set flagged of newTask to true" if flagged else ""
    est_line = f"set estimated minutes of newTask to {estimated_minutes}" if estimated_minutes else ""

    script = date_pre_script + f'''
try
 tell application "OmniFocus"
  tell front document
   set newTask to missing value
   set parentTask to missing value

   if "{parent_task_id}" is not "" then
    try
     set parentTask to first flattened task where id = "{parent_task_id}"
    end try
    if parentTask is missing value then
     try
      set parentTask to first inbox task where id = "{parent_task_id}"
     end try
    end if
   end if

   if parentTask is missing value and "{parent_task_name}" is not "" then
    try
     set parentTask to first flattened task where name = "{parent_task_name}"
    end try
    if parentTask is missing value then
     try
      set parentTask to first inbox task where name = "{parent_task_name}"
     end try
    end if
   end if

   if parentTask is not missing value then
    set newTask to make new task with properties {{name:"{name}"}} at end of tasks of parentTask
   else if "{project_name}" is not "" then
    try
     set theProject to first flattened project where name = "{project_name}"
     set newTask to make new task with properties {{name:"{name}"}} at end of tasks of theProject
    on error
     return "{{\\"success\\":false,\\"error\\":\\"Project not found: {project_name}\\"}}"
    end try
   else
    set newTask to make new inbox task with properties {{name:"{name}"}}
   end if

   {note_line}
   {due_line}
   {defer_line}
   {planned_line}
   {flag_line}
   {est_line}
   {tag_script}
   set taskId to id of newTask as string
   return "{{\\"success\\":true,\\"taskId\\":\\"" & taskId & "\\",\\"name\\":\\"{name}\\"}}"
  end tell
 end tell
on error errorMessage
 return "{{\\"success\\":false,\\"error\\":\\"" & errorMessage & "\\"}}"
end try
'''
    return script


def gen_add_project(
    name: str,
    note: str = "",
    due_date: str = "",
    defer_date: str = "",
    flagged: bool = False,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
    folder_name: str = "",
    sequential: bool = False,
) -> str:
    """Generate AppleScript to add a project to OmniFocus."""
    name = _sanitize(name)
    note = _sanitize(note)
    folder_name = _sanitize(folder_name)
    tags = tags or []

    date_pre = []
    due_var = defer_var = ""
    if due_date:
        due_var, s = _date_var(due_date)
        date_pre.append(s)
    if defer_date:
        defer_var, s = _date_var(defer_date)
        date_pre.append(s)
    date_pre_script = "\n\n".join(date_pre) + "\n\n" if date_pre else ""

    tag_script = ""
    for tag in tags:
        t = _sanitize(tag)
        tag_script += f'''
 try
  set theTag to first flattened tag where name = "{t}"
  add theTag to tags of newProject
 on error
  try
   set theTag to make new tag with properties {{name:"{t}"}}
   add theTag to tags of newProject
  on error
  end try
 end try'''

    if folder_name:
        folder_block = f'''
 try
  set theFolder to first flattened folder where name = "{folder_name}"
  set newProject to make new project with properties {{name:"{name}"}} at end of projects of theFolder
 on error
  return "{{\\"success\\":false,\\"error\\":\\"Folder not found: {folder_name}\\"}}"
 end try'''
    else:
        folder_block = f'set newProject to make new project with properties {{name:"{name}"}}'

    note_line = f'set note of newProject to "{note}"' if note else ""
    due_line = f"set due date of newProject to {due_var}" if due_var else ""
    defer_line = f"set defer date of newProject to {defer_var}" if defer_var else ""
    flag_line = "set flagged of newProject to true" if flagged else ""
    est_line = f"set estimated minutes of newProject to {estimated_minutes}" if estimated_minutes else ""

    script = date_pre_script + f'''
try
 tell application "OmniFocus"
  tell front document
   {folder_block}
   {note_line}
   {due_line}
   {defer_line}
   {flag_line}
   {est_line}
   set sequential of newProject to {str(sequential).lower()}
   {tag_script}
   set projectId to id of newProject as string
   return "{{\\"success\\":true,\\"projectId\\":\\"" & projectId & "\\",\\"name\\":\\"{name}\\"}}"
  end tell
 end tell
on error errorMessage
 return "{{\\"success\\":false,\\"error\\":\\"" & errorMessage & "\\"}}"
end try
'''
    return script


def _find_block_task(item_id: str = "", name: str = "") -> str:
    """Generate AppleScript to find a task by id and/or name.

    Uses `contents of` to dereference loop variables so the returned
    reference is safe to pass to `delete` or property setters.
    """
    blocks = []
    if item_id:
        blocks.append(f'''
   repeat with aTask in (flattened tasks)
    if (id of aTask as string) = "{item_id}" then
     set foundItem to contents of aTask
     exit repeat
    end if
   end repeat
   if foundItem is missing value then
    repeat with aTask in (inbox tasks)
     if (id of aTask as string) = "{item_id}" then
      set foundItem to contents of aTask
      exit repeat
     end if
    end repeat
   end if''')
    if name:
        guard = "if foundItem is missing value then\n    " if item_id else ""
        end_guard = "\n   end if" if item_id else ""
        blocks.append(f'''
   {guard}repeat with aTask in (flattened tasks)
    if (name of aTask) = "{name}" then
     set foundItem to contents of aTask
     exit repeat
    end if
   end repeat{end_guard}
   if foundItem is missing value then
    repeat with aTask in (inbox tasks)
     if (name of aTask) = "{name}" then
      set foundItem to contents of aTask
      exit repeat
     end if
    end repeat
   end if''')
    return "\n".join(blocks)


def _find_block_project(item_id: str = "", name: str = "") -> str:
    """Generate AppleScript to find a project by id and/or name."""
    blocks = []
    if item_id:
        blocks.append(f'''
   repeat with aProject in (flattened projects)
    if (id of aProject as string) = "{item_id}" then
     set foundItem to contents of aProject
     exit repeat
    end if
   end repeat''')
    if name:
        guard = "if foundItem is missing value then\n    " if item_id else ""
        end_guard = "\n   end if" if item_id else ""
        blocks.append(f'''
   {guard}repeat with aProject in (flattened projects)
    if (name of aProject) = "{name}" then
     set foundItem to contents of aProject
     exit repeat
    end if
   end repeat{end_guard}''')
    return "\n".join(blocks)


def gen_remove_item(item_id: str = "", name: str = "", item_type: str = "task") -> str:
    """Generate AppleScript to remove a task or project."""
    item_id = _sanitize(item_id)
    name = _sanitize(name)
    if not item_id and not name:
        return 'return "{\\"success\\":false,\\"error\\":\\"Either id or name must be provided\\"}"'

    if item_type == "task":
        find_block = _find_block_task(item_id, name)
    else:
        find_block = _find_block_project(item_id, name)

    return f'''
try
 tell application "OmniFocus"
  tell front document
   set foundItem to missing value
   {find_block}
   if foundItem is not missing value then
    set itemName to name of foundItem
    set itemId to id of foundItem as string
    delete foundItem
    return "{{\\"success\\":true,\\"id\\":\\"" & itemId & "\\",\\"name\\":\\"" & itemName & "\\"}}"
   else
    return "{{\\"success\\":false,\\"error\\":\\"Item not found\\"}}"
   end if
  end tell
 end tell
on error errorMessage
 return "{{\\"success\\":false,\\"error\\":\\"" & errorMessage & "\\"}}"
end try
'''


def gen_edit_item(
    item_type: str = "task",
    item_id: str = "",
    item_name: str = "",
    new_name: str | None = None,
    new_note: str | None = None,
    new_due_date: str | None = None,
    new_defer_date: str | None = None,
    new_planned_date: str | None = None,
    new_flagged: bool | None = None,
) -> str:
    """Generate AppleScript to edit a task or project. Use empty string to clear dates."""
    if not item_id and not item_name:
        return 'return "{\\"success\\":false,\\"error\\":\\"Either id or name must be provided\\"}"'
    find_script = gen_remove_item(item_id=item_id, name=item_name, item_type=item_type)
    find_script = find_script.replace("delete foundItem", "%%EDIT%%")
    find_script = find_script.replace(
        'return "{\\"success\\":true,\\"id\\":\\"" & itemId & "\\",\\"name\\":\\"" & itemName & "\\"}"',
        "%%DONE%%",
    )
    edits = []
    if new_name is not None:
        edits.append(f'set name of foundItem to "{_sanitize(new_name)}"')
    if new_note is not None:
        edits.append(f'set note of foundItem to "{_sanitize(new_note)}"')
    if new_flagged is not None:
        edits.append(f"set flagged of foundItem to {str(new_flagged).lower()}")
    date_pre = []
    if new_due_date is not None:
        if new_due_date == "":
            edits.append("set due date of foundItem to missing value")
        else:
            v, s = _date_var(new_due_date)
            date_pre.append(s)
            edits.append(f"set due date of foundItem to {v}")
    if new_defer_date is not None:
        if new_defer_date == "":
            edits.append("set defer date of foundItem to missing value")
        else:
            v, s = _date_var(new_defer_date)
            date_pre.append(s)
            edits.append(f"set defer date of foundItem to {v}")
    if new_planned_date is not None and item_type == "task":
        if new_planned_date == "":
            edits.append("set planned date of foundItem to missing value")
        else:
            v, s = _date_var(new_planned_date)
            date_pre.append(s)
            edits.append(f"set planned date of foundItem to {v}")
    edit_block = "\n    ".join(edits) if edits else "set itemName to name of foundItem"
    pre = "\n\n".join(date_pre) + "\n\n" if date_pre else ""
    script = find_script.replace("%%EDIT%%", edit_block)
    script = script.replace("%%DONE%%", 'return "{\\"success\\":true,\\"name\\":\\"" & name of foundItem & "\\"}"')
    return pre + script


