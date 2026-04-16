"""Unit tests for input validation and security hardening.

These tests do NOT require OmniFocus to be running.
"""

from __future__ import annotations

from datetime import date

import pytest

from pymnifocus.query_generator import (
    VALID_ENTITIES,
    VALID_SORT_FIELDS,
    generate_query_script,
)
from pymnifocus import cli as pymnifocus_cli
from pymnifocus.applescript_gen import _sanitize


class TestQueryGeneratorValidation:
    """Verify whitelisting and input validation in the query generator."""

    def test_valid_entities_accepted(self):
        for entity in VALID_ENTITIES:
            script = generate_query_script(entity=entity)
            assert "entityType" in script

    def test_invalid_entity_rejected(self):
        with pytest.raises(ValueError, match="Invalid entity"):
            generate_query_script(entity="users")

    def test_entity_injection_rejected(self):
        with pytest.raises(ValueError, match="Invalid entity"):
            generate_query_script(entity='"; process.exit(); //')

    def test_valid_sort_fields_accepted(self):
        for field in VALID_SORT_FIELDS:
            script = generate_query_script(entity="tasks", sort_by=field)
            assert "filtered.sort" in script

    def test_invalid_sort_field_rejected(self):
        with pytest.raises(ValueError, match="Invalid sort_by"):
            generate_query_script(entity="tasks", sort_by="id; malicious()")

    def test_valid_fields_accepted(self):
        script = generate_query_script(entity="tasks", fields=["id", "name", "dueDate"])
        assert "item.id.primaryKey" in script

    def test_unknown_field_rejected(self):
        with pytest.raises(ValueError, match="Unknown field"):
            generate_query_script(entity="tasks", fields=["name", "evil_injection"])

    def test_limit_must_be_integer(self):
        with pytest.raises(ValueError, match="must be an integer"):
            generate_query_script(entity="tasks", limit="DROP TABLE")

    def test_limit_capped_at_max(self):
        script = generate_query_script(entity="tasks", limit=999999)
        assert "5000" in script
        assert "999999" not in script

    def test_limit_negative_coerced(self):
        script = generate_query_script(entity="tasks", limit=-5)
        assert "slice(0, -5)" in script

    def test_numeric_filter_validated(self):
        with pytest.raises(ValueError, match="must be an integer"):
            generate_query_script(
                entity="tasks",
                filters={"dueWithin": "7; evil()"},
            )

    def test_numeric_filter_accepted(self):
        script = generate_query_script(
            entity="tasks",
            filters={"dueWithin": 7},
        )
        assert "checkDateFilter(item.dueDate, 7)" in script

    def test_completion_date_filters_in_script(self):
        script = generate_query_script(
            entity="tasks",
            filters={"completedAfter": "2026-04-09", "completedBefore": "2026-04-16"},
        )
        assert "hasCompletedAfterFilter" in script
        assert "hasCompletedBeforeFilter" in script
        assert "completedAfterMsBound" in script
        assert "completedBeforeMsBound" in script
        assert "item.completionDate.getTime()" in script

    def test_tags_field_alias_maps_to_tag_names(self):
        script = generate_query_script(entity="tasks", fields=["name", "tags"])
        assert "item.tags.map(t => t.name)" in script

    def test_invalid_completion_filter_rejected(self):
        with pytest.raises(ValueError, match="completedAfter"):
            generate_query_script(
                entity="tasks",
                filters={"completedAfter": "not-a-date"},
            )

    def test_sort_order_sanitized(self):
        script = generate_query_script(
            entity="tasks", sort_by="name", sort_order="invalid"
        )
        assert "* 1" in script  # defaults to asc

    def test_default_field_mapping_tasks(self):
        script = generate_query_script(entity="tasks")
        assert "item.id.primaryKey" in script
        assert "taskStatusMap" in script

    def test_default_field_mapping_projects(self):
        script = generate_query_script(entity="projects")
        assert "projectStatusMap" in script

    def test_default_field_mapping_folders(self):
        script = generate_query_script(entity="folders")
        assert "projectCount" in script


class TestCliCompletedWithinMerge:
    """pymnifocus-query --completed-within builds the same filter window as the MCP."""

    def test_seven_days_inclusive_of_today(self):
        q: dict = {"entity": "tasks", "filters": {}}
        pymnifocus_cli._merge_completed_within(q, 7, today=date(2026, 4, 16))
        assert q["includeCompleted"] is True
        assert q["filters"]["completedAfter"] == "2026-04-09"
        assert q["filters"]["completedBefore"] == "2026-04-17"

    def test_zero_days_is_today_only(self):
        q: dict = {"entity": "tasks", "filters": {}}
        pymnifocus_cli._merge_completed_within(q, 0, today=date(2026, 4, 16))
        assert q["filters"]["completedAfter"] == "2026-04-16"
        assert q["filters"]["completedBefore"] == "2026-04-17"

    def test_negative_days_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            pymnifocus_cli._merge_completed_within({"entity": "tasks", "filters": {}}, -1)


class TestAppleScriptSanitization:
    """Verify _sanitize prevents injection."""

    def test_quotes_escaped(self):
        assert _sanitize('hello "world"') == 'hello \\"world\\"'

    def test_backslashes_escaped(self):
        assert _sanitize("path\\to\\file") == "path\\\\to\\\\file"

    def test_newlines_escaped(self):
        assert _sanitize("line1\nline2") == "line1\\nline2"

    def test_carriage_returns_escaped(self):
        assert _sanitize("line1\rline2") == "line1\\rline2"

    def test_tabs_escaped(self):
        assert _sanitize("col1\tcol2") == "col1\\tcol2"

    def test_empty_string(self):
        assert _sanitize("") == ""

    def test_none_safe(self):
        assert _sanitize(None) == ""

    def test_injection_attempt_neutralized(self):
        malicious = 'foo\ntell application "System Events" to keystroke "q"'
        result = _sanitize(malicious)
        assert "\n" not in result
        assert "\\n" in result
