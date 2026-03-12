"""Shared fixtures for pymnifocus tests."""

from __future__ import annotations

import uuid

import pytest

TEST_TASK_PREFIX = "_pymnifocus_test_"


@pytest.fixture
def test_task_name():
    """Generate a unique, identifiable test task name."""
    return f"{TEST_TASK_PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True, scope="session")
def cleanup_stale_test_tasks():
    """After all tests, remove any leftover test tasks from prior failed runs."""
    yield
    try:
        from pymnifocus.omnifocus import query_omnifocus, execute_applescript
        from pymnifocus.applescript_gen import gen_remove_item

        result = query_omnifocus({
            "entity": "tasks",
            "includeCompleted": True,
            "limit": 200,
        })
        if not result.get("success"):
            return
        for task in result.get("items") or []:
            if task.get("name", "").startswith(TEST_TASK_PREFIX):
                try:
                    script = gen_remove_item(item_id=task["id"], item_type="task")
                    execute_applescript(script)
                except Exception:
                    pass
    except Exception:
        pass
