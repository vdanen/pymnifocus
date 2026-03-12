# pymnifocus

A Python toolkit for [OmniFocus](https://www.omnigroup.com/omnifocus) on macOS: an MCP server for AI assistant integration (Cursor, Claude, Gemini) and a standalone CLI query tool.

Inspired by [themotionmachine/OmniFocus-MCP](https://github.com/themotionmachine/OmniFocus-MCP), rebuilt in Python with security hardening, a CLI, and PyPI packaging.

## Prerequisites

- **macOS** with OmniFocus installed and running
- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip

## Installation

```bash
# From PyPI
pip install pymnifocus

# Or with uv
uv pip install pymnifocus

# For development
git clone https://github.com/vdanen/pymnifocus.git
cd pymnifocus
uv sync
pip install -e .
```

## CLI Query Tool

Query OmniFocus directly from your terminal with `pymnifocus-query`:

```bash
# Shorthand flags
pymnifocus-query --overdue
pymnifocus-query --flagged --sort dueDate
pymnifocus-query --inbox
pymnifocus-query --due-within 7 --limit 10
pymnifocus-query --project "Weekly Review"
pymnifocus-query --tag work --tag urgent
pymnifocus-query --available --summary
pymnifocus-query --today

# JSON input (same format as MCP query_omnifocus tool)
pymnifocus-query '{"entity": "tasks", "filters": {"status": ["Overdue", "DueSoon"]}, "sortBy": "dueDate"}'

# Pipe from stdin
echo '{"entity": "projects", "filters": {"status": ["Active"]}}' | pymnifocus-query

# Other tools
pymnifocus-query --tags
pymnifocus-query --perspectives
pymnifocus-query --dump

# Raw JSON output (for scripting)
pymnifocus-query --overdue --json
```

Run `pymnifocus-query --help` for full usage.

## MCP Server

The MCP server enables AI assistants to interact with OmniFocus through natural language.

### Running the Server

```bash
# Stdio transport (for Cursor/Claude/Gemini)
pymnifocus-server

# Or via module
python -m pymnifocus
```

### Cursor Integration

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "omnifocus": {
      "command": "pymnifocus-server"
    }
  }
}
```

Or if using `uv` from a local clone:

```json
{
  "mcpServers": {
    "omnifocus": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/path/to/pymnifocus",
        "python",
        "-m",
        "pymnifocus.server"
      ]
    }
  }
}
```

Restart Cursor or reload MCP servers (`Cmd+Shift+P` -> "MCP: Restart Servers").

### Claude Desktop Integration

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "omnifocus": {
      "command": "pymnifocus-server"
    }
  }
}
```

Restart Claude Desktop.

### Google AI Studio / Gemini

For MCP-compatible Gemini clients, the server uses **stdio** transport by default:

- **Command:** `pymnifocus-server`

For **Streamable HTTP** (web-based clients):

```bash
python -c "from pymnifocus.server import mcp; mcp.run(transport='streamable-http')"
```

Then connect to `http://localhost:8000/mcp`.

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `query_omnifocus` | Query tasks, projects, or folders with filters |
| `dump_database` | Get full OmniFocus database state |
| `add_omnifocus_task` | Add a new task |
| `add_project` | Add a new project |
| `remove_item` | Remove a task or project |
| `edit_item` | Edit a task or project |
| `batch_add_items` | Add multiple items at once (max 100) |
| `batch_remove_items` | Remove multiple items at once (max 100) |
| `list_perspectives` | List available perspectives |
| `get_perspective_view` | Get items from a perspective |
| `list_tags` | List all tags with hierarchy |

## MCP Resources

| URI | Description |
|-----|-------------|
| `omnifocus://inbox` | Current inbox items |
| `omnifocus://today` | Today's agenda (due, planned, overdue) |
| `omnifocus://flagged` | All flagged items |
| `omnifocus://stats` | Database statistics |
| `omnifocus://project/{name}` | Tasks in a project |
| `omnifocus://perspective/{name}` | Items in a perspective |

## Example Prompts

- "Show me all flagged tasks due this week"
- "Add a task 'Review quarterly report' to my Work project, due Friday"
- "What's in my inbox?"
- "List all my projects"
- "Create a project called 'Website Redesign' with 3 tasks"

## How It Works

The server communicates with OmniFocus using:

- **OmniJS** scripts executed via JXA (`osascript -l JavaScript`) for queries, dumps, perspectives, and tags
- **AppleScript** for add/edit/remove operations

OmniFocus must be running for either the MCP server or the CLI tool to function.

## Security

- All user input is validated and escaped before embedding in generated scripts
- Entity names, sort fields, and field names are whitelisted
- Numeric parameters are validated as integers
- AppleScript strings are sanitized against injection (quotes, backslashes, newlines)
- Script paths are constrained to prevent directory traversal
- Batch operations are capped at 100 items
- Query results are capped at 5000 items
- All communication is local (no network traffic)

## License

MIT

## Credits

Inspired by [themotionmachine/OmniFocus-MCP](https://github.com/themotionmachine/OmniFocus-MCP). OmniJS scripts are adapted from that project.
