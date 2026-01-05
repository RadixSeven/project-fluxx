"""Migration logic for upgrading project files between versions.

Each migration function transforms JSON data from one version to the next.
"""

from datetime import UTC, datetime, timedelta

from fluxx.data.json_types import JsonObject

# Current version of the file format
CURRENT_VERSION = "1.2"

# Versions we can migrate from
SUPPORTED_VERSIONS = ["1.0", "1.1", "1.2"]


class MigrationError(Exception):
    """Raised when migration fails."""

    pass


def migrate_project_data(json_data: JsonObject) -> JsonObject:
    """Migrate project JSON data to the current version.

    Args:
        json_data: The raw JSON data from the project file

    Returns:
        Migrated JSON data in the current version format

    Raises:
        MigrationError: If migration fails or version is unsupported
    """
    version = json_data.get("version", "1.0")

    if version not in SUPPORTED_VERSIONS:
        raise MigrationError(
            f"Cannot migrate from version {version}. "
            f"Supported versions: {SUPPORTED_VERSIONS}"
        )

    # Apply migrations in sequence
    if version == "1.0":
        json_data = migrate_1_0_to_1_1(json_data)
        version = "1.1"  # Update version for next migration in chain

    if version == "1.1":
        json_data = migrate_1_1_to_1_2(json_data)

    return json_data


def migrate_1_0_to_1_1(json_data: JsonObject) -> JsonObject:
    """Migrate from version 1.0 to 1.1.

    Changes:
    - Task completion tracking: replaces actual_start_time, actual_assignee,
      actual_duration with a completion object (NotStartedCompletion,
      StartedCompletion, or DoneCompletion)

    Args:
        json_data: Project data in version 1.0 format

    Returns:
        Project data in version 1.1 format
    """
    migration_time = datetime.now(UTC)

    # Get workers for hours_per_workday lookup
    workers_by_id: dict[str, float] = {}
    workers_list = json_data.get("workers", [])
    if isinstance(workers_list, list):
        for worker in workers_list:
            if isinstance(worker, dict):
                worker_id = worker.get("id")
                hours = worker.get("hours_per_workday", 8.0)
                if isinstance(worker_id, str) and isinstance(hours, (int, float)):
                    workers_by_id[worker_id] = float(hours)

    # Migrate persistent tasks
    persistent_tasks = json_data.get("persistent_tasks", {})
    if isinstance(persistent_tasks, dict):
        for _persistent_id, persistent_task in persistent_tasks.items():
            if isinstance(persistent_task, dict):
                versions = persistent_task.get("versions", {})
                if isinstance(versions, dict):
                    for _version_id, task in versions.items():
                        if isinstance(task, dict):
                            _migrate_task_completion(
                                task, migration_time, workers_by_id
                            )

    # Update version
    json_data["version"] = "1.1"

    return json_data


def _migrate_task_completion(
    task: JsonObject,
    migration_time: datetime,
    workers_by_id: dict[str, float],
) -> None:
    """Migrate a single task's completion fields in place.

    Args:
        task: Task dict to migrate (modified in place)
        migration_time: When the migration is happening
        workers_by_id: Map of worker ID to hours_per_workday
    """
    # Extract old fields
    actual_start_time_str = task.pop("actual_start_time", None)
    actual_assignee = task.pop("actual_assignee", None)
    actual_duration = task.pop("actual_duration", None)

    # Determine completion state
    if not isinstance(actual_start_time_str, str) or not isinstance(
        actual_assignee, str
    ):
        # Not started (or invalid data)
        task["completion"] = {"status": "not_started"}
    elif actual_duration is None:
        # Started but not done - need to estimate hours_logged
        actual_start_time = datetime.fromisoformat(actual_start_time_str)
        hours_per_workday = workers_by_id.get(actual_assignee, 8.0)

        # Calculate work days elapsed (rough estimate)
        elapsed = migration_time - actual_start_time
        elapsed_days = elapsed.total_seconds() / (24 * 60 * 60)
        # Rough estimate: 5/7 days are workdays
        work_days = elapsed_days * 5 / 7
        hours_logged = work_days * hours_per_workday

        # Clamp to at least 0
        hours_logged = max(0.0, hours_logged)

        task["completion"] = {
            "status": "started",
            "assignee": actual_assignee,
            "start_time": actual_start_time_str,
            "hours_logged": hours_logged,
        }
    elif isinstance(actual_duration, (int, float)):
        # Done - calculate end_time from start_time and duration
        actual_start_time = datetime.fromisoformat(actual_start_time_str)
        hours_per_workday = workers_by_id.get(actual_assignee, 8.0)

        # Calculate approximate end time
        work_days = float(actual_duration) / hours_per_workday
        # Rough estimate: each work day = 7/5 calendar days on average
        calendar_days = work_days * 7 / 5
        end_time = actual_start_time + timedelta(days=calendar_days)

        task["completion"] = {
            "status": "done",
            "assignee": actual_assignee,
            "start_time": actual_start_time_str,
            "hours_logged": float(actual_duration),
            "end_time": end_time.isoformat(),
        }
    else:
        # Fallback for invalid duration type
        task["completion"] = {"status": "not_started"}


def migrate_1_1_to_1_2(json_data: JsonObject) -> JsonObject:
    """Migrate from version 1.1 to 1.2.

    Changes:
    - Adds jira_config field to Project (optional, defaults to None)
    - Task model gets jira_reference and jira_issue_type fields (optional, default None)
    - Worker model gets jira_account_id field (optional, default None)
    - Task.duration_distribution now supports JiraDurationDistribution

    All new fields have default values of None, so no data transformation is needed.
    This migration only updates the version number.

    Args:
        json_data: Project data in version 1.1 format

    Returns:
        Project data in version 1.2 format
    """
    # Update version
    json_data["version"] = "1.2"

    return json_data
