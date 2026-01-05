"""Tests for migration logic."""

from datetime import UTC, datetime

import pytest

from fluxx.data.json_types import JsonObject
from fluxx.data.migration import (
    CURRENT_VERSION,
    MigrationError,
    _migrate_task_completion,
    migrate_1_0_to_1_1,
    migrate_1_1_to_1_2,
    migrate_project_data,
)


class TestMigrateProjectData:
    """Tests for migrate_project_data function."""

    def test_migrate_from_current_version_is_noop(self) -> None:
        """Migrating from current version should be a no-op."""
        json_data: JsonObject = {
            "version": CURRENT_VERSION,
            "metadata": {"name": "Test"},
            "persistent_tasks": {},
        }
        result = migrate_project_data(json_data)
        assert result["version"] == CURRENT_VERSION

    def test_migrate_from_unsupported_version_raises(self) -> None:
        """Migrating from unsupported version should raise."""
        json_data: JsonObject = {"version": "0.5"}
        with pytest.raises(MigrationError, match="Cannot migrate from version 0.5"):
            migrate_project_data(json_data)

    def test_migrate_from_1_0_to_current(self) -> None:
        """Migrating from 1.0 should update to current version."""
        json_data: JsonObject = {
            "version": "1.0",
            "workers": [],
            "persistent_tasks": {},
        }
        result = migrate_project_data(json_data)
        assert result["version"] == CURRENT_VERSION


class TestMigrateV1ToV11:
    """Tests for migrate_1_0_to_1_1 function."""

    def test_task_not_started(self) -> None:
        """Task with no completion fields should become NotStartedCompletion."""
        json_data: JsonObject = {
            "version": "1.0",
            "workers": [],
            "persistent_tasks": {
                "p1": {
                    "id": "p1",
                    "versions": {
                        "v1": {
                            "id": "t1",
                            "title": "Task",
                            "description": "Test",
                        }
                    },
                }
            },
        }
        result = migrate_1_0_to_1_1(json_data)
        persistent_tasks = result["persistent_tasks"]
        assert isinstance(persistent_tasks, dict)
        p1 = persistent_tasks["p1"]
        assert isinstance(p1, dict)
        versions = p1["versions"]
        assert isinstance(versions, dict)
        task = versions["v1"]
        assert isinstance(task, dict)
        assert task["completion"] == {"status": "not_started"}
        assert "actual_start_time" not in task
        assert "actual_assignee" not in task
        assert "actual_duration" not in task

    def test_task_started(self) -> None:
        """Task with start time and assignee should become StartedCompletion."""
        json_data: JsonObject = {
            "version": "1.0",
            "workers": [{"id": "w1", "name": "Alice", "hours_per_workday": 8.0}],
            "persistent_tasks": {
                "p1": {
                    "id": "p1",
                    "versions": {
                        "v1": {
                            "id": "t1",
                            "title": "Task",
                            "description": "Test",
                            "actual_start_time": "2024-01-15T10:00:00+00:00",
                            "actual_assignee": "w1",
                        }
                    },
                }
            },
        }
        result = migrate_1_0_to_1_1(json_data)
        persistent_tasks = result["persistent_tasks"]
        assert isinstance(persistent_tasks, dict)
        p1 = persistent_tasks["p1"]
        assert isinstance(p1, dict)
        versions = p1["versions"]
        assert isinstance(versions, dict)
        task = versions["v1"]
        assert isinstance(task, dict)
        completion = task["completion"]
        assert isinstance(completion, dict)
        assert completion["status"] == "started"
        assert completion["assignee"] == "w1"
        assert completion["start_time"] == "2024-01-15T10:00:00+00:00"
        assert "hours_logged" in completion
        hours_logged = completion["hours_logged"]
        assert isinstance(hours_logged, (int, float))
        assert hours_logged >= 0

    def test_task_done(self) -> None:
        """Task with all completion fields should become DoneCompletion."""
        json_data: JsonObject = {
            "version": "1.0",
            "workers": [{"id": "w1", "name": "Alice", "hours_per_workday": 8.0}],
            "persistent_tasks": {
                "p1": {
                    "id": "p1",
                    "versions": {
                        "v1": {
                            "id": "t1",
                            "title": "Task",
                            "description": "Test",
                            "actual_start_time": "2024-01-15T10:00:00+00:00",
                            "actual_assignee": "w1",
                            "actual_duration": 16.0,
                        }
                    },
                }
            },
        }
        result = migrate_1_0_to_1_1(json_data)
        persistent_tasks = result["persistent_tasks"]
        assert isinstance(persistent_tasks, dict)
        p1 = persistent_tasks["p1"]
        assert isinstance(p1, dict)
        versions = p1["versions"]
        assert isinstance(versions, dict)
        task = versions["v1"]
        assert isinstance(task, dict)
        completion = task["completion"]
        assert isinstance(completion, dict)
        assert completion["status"] == "done"
        assert completion["assignee"] == "w1"
        assert completion["start_time"] == "2024-01-15T10:00:00+00:00"
        assert completion["hours_logged"] == 16.0
        assert "end_time" in completion


class TestMigrateTaskCompletion:
    """Tests for _migrate_task_completion helper."""

    def test_not_started_no_fields(self) -> None:
        """Task with no fields becomes not started."""
        task: JsonObject = {}
        migration_time = datetime.now(UTC)
        _migrate_task_completion(task, migration_time, {})
        assert task["completion"] == {"status": "not_started"}

    def test_started_uses_worker_hours(self) -> None:
        """Started task uses worker's hours_per_workday."""
        task: JsonObject = {
            "actual_start_time": "2024-01-15T10:00:00+00:00",
            "actual_assignee": "w1",
        }
        migration_time = datetime(2024, 1, 16, 10, 0, 0, tzinfo=UTC)  # 1 day later
        workers_by_id = {"w1": 6.0}  # 6 hours per workday
        _migrate_task_completion(task, migration_time, workers_by_id)

        completion = task["completion"]
        assert isinstance(completion, dict)
        assert completion["status"] == "started"
        # 1 calendar day * 5/7 work days * 6 hours = ~4.3 hours
        hours_logged = completion["hours_logged"]
        assert isinstance(hours_logged, (int, float))
        assert hours_logged > 0

    def test_started_uses_default_hours_if_worker_unknown(self) -> None:
        """Started task uses 8 hours default if worker not found."""
        task: JsonObject = {
            "actual_start_time": "2024-01-15T10:00:00+00:00",
            "actual_assignee": "w_unknown",
        }
        migration_time = datetime(2024, 1, 16, 10, 0, 0, tzinfo=UTC)
        _migrate_task_completion(task, migration_time, {})

        completion = task["completion"]
        assert isinstance(completion, dict)
        assert completion["status"] == "started"
        # Should use 8 hours default
        hours_logged = completion["hours_logged"]
        assert isinstance(hours_logged, (int, float))
        assert hours_logged > 0

    def test_done_calculates_end_time(self) -> None:
        """Done task calculates end_time from start and duration."""
        task: JsonObject = {
            "actual_start_time": "2024-01-15T10:00:00+00:00",
            "actual_assignee": "w1",
            "actual_duration": 8.0,
        }
        migration_time = datetime.now(UTC)
        workers_by_id = {"w1": 8.0}
        _migrate_task_completion(task, migration_time, workers_by_id)

        completion = task["completion"]
        assert isinstance(completion, dict)
        assert completion["status"] == "done"
        assert completion["hours_logged"] == 8.0
        # end_time should be after start_time
        end_time = completion["end_time"]
        start_time = completion["start_time"]
        assert isinstance(end_time, str) and isinstance(start_time, str)
        assert end_time > start_time

    def test_invalid_duration_type_becomes_not_started(self) -> None:
        """Task with invalid duration type falls back to not started."""
        task: JsonObject = {
            "actual_start_time": "2024-01-15T10:00:00+00:00",
            "actual_assignee": "w1",
            "actual_duration": "invalid",  # Should be a number, not string
        }
        migration_time = datetime.now(UTC)
        _migrate_task_completion(task, migration_time, {})

        assert task["completion"] == {"status": "not_started"}


class TestMigrateV11ToV12:
    """Tests for migrate_1_1_to_1_2 function."""

    def test_updates_version(self) -> None:
        """Migration updates version to 1.2."""
        json_data: JsonObject = {
            "version": "1.1",
            "workers": [],
            "persistent_tasks": {},
        }
        result = migrate_1_1_to_1_2(json_data)
        assert result["version"] == "1.2"

    def test_preserves_existing_data(self) -> None:
        """Migration preserves existing project data."""
        json_data: JsonObject = {
            "version": "1.1",
            "metadata": {"name": "Test Project"},
            "workers": [{"id": "w1", "name": "Alice", "hours_per_workday": 8.0}],
            "persistent_tasks": {
                "p1": {
                    "id": "p1",
                    "versions": {
                        "v1": {
                            "id": "t1",
                            "title": "Task",
                            "description": "Test",
                            "completion": {"status": "not_started"},
                        }
                    },
                }
            },
        }
        result = migrate_1_1_to_1_2(json_data)

        # Data should be preserved
        assert result["metadata"] == {"name": "Test Project"}
        workers = result["workers"]
        assert isinstance(workers, list)
        assert len(workers) == 1
        persistent_tasks = result["persistent_tasks"]
        assert isinstance(persistent_tasks, dict)
        assert "p1" in persistent_tasks

    def test_migrate_from_1_1_to_current(self) -> None:
        """Migrating from 1.1 should update to current version."""
        json_data: JsonObject = {
            "version": "1.1",
            "workers": [],
            "persistent_tasks": {},
        }
        result = migrate_project_data(json_data)
        assert result["version"] == CURRENT_VERSION

    def test_migrate_chain_1_0_to_current(self) -> None:
        """Migrating from 1.0 should chain through 1.1 to current."""
        json_data: JsonObject = {
            "version": "1.0",
            "workers": [],
            "persistent_tasks": {
                "p1": {
                    "id": "p1",
                    "versions": {
                        "v1": {
                            "id": "t1",
                            "title": "Task",
                            "description": "Test",
                            "actual_start_time": "2024-01-15T10:00:00+00:00",
                            "actual_assignee": "w1",
                        }
                    },
                }
            },
        }
        result = migrate_project_data(json_data)
        assert result["version"] == CURRENT_VERSION
        # Should have completion from 1.0->1.1 migration
        persistent_tasks = result["persistent_tasks"]
        assert isinstance(persistent_tasks, dict)
        p1 = persistent_tasks["p1"]
        assert isinstance(p1, dict)
        versions = p1["versions"]
        assert isinstance(versions, dict)
        task = versions["v1"]
        assert isinstance(task, dict)
        assert "completion" in task
