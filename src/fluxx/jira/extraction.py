"""Data extraction from Jira API responses to Fluxx models.

This module converts Jira issue data into Fluxx task structures.
We use "extract" rather than "map" to emphasize that we're converting
part of the data from Jira's representation to Fluxx's representation.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fluxx.data.id_generation import generate_task_id, generate_worker_id
from fluxx.data.models import (
    DoneCompletion,
    JiraDurationDistribution,
    NotStartedCompletion,
    StartedCompletion,
    Task,
    TaskCompletion,
    TaskId,
    Worker,
    WorkerId,
)
from fluxx.jira.api_types import (
    JiraIssueResponse,
    JiraWorklogEntry,
)
from fluxx.jira.models import JiraIssueKey, JiraReference

logger = logging.getLogger(__name__)

# Constants
EPSILON_HOURS = 1e-6  # Minimum hours for zero-work completed tasks


@dataclass
class ExtractedCompletion:
    """Result of extracting completion status from a Jira issue."""

    completion: TaskCompletion
    allowed_workers: list[WorkerId] | None = None


@dataclass
class ExtractedDependency:
    """A dependency extracted from a Jira issue link."""

    target_key: str  # Issue key this depends on


@dataclass
class HierarchyEntry:
    """Entry in the extracted hierarchy."""

    issue_key: str
    parent_key: str | None = None


@dataclass
class HierarchyWarning:
    """Warning generated during hierarchy extraction."""

    issue_key: str
    message: str


@dataclass
class ExtractedHierarchy:
    """Result of extracting hierarchy from issues."""

    entries: dict[str, HierarchyEntry]
    warnings: list[HierarchyWarning]


def parse_jira_datetime(
    datetime_str: str,
    server_timezone: str = "UTC",
) -> datetime:
    """Parse a Jira datetime string to a naive datetime object.

    Jira uses ISO 8601 format with various timezone representations:
    - 2024-01-15T10:00:00.000+0000 (positive offset)
    - 2024-01-15T10:00:00.000-0500 (negative offset)
    - 2024-01-15T10:00:00.000Z (UTC)
    - 2024-01-15T10:00:00 (no timezone - uses server_timezone fallback)

    Args:
        datetime_str: ISO 8601 datetime string from Jira API
        server_timezone: IANA timezone name to use if the string has no
            timezone info (e.g., 'America/New_York'). Defaults to 'UTC'.

    Returns:
        Naive datetime for consistency with Fluxx models. The timezone-aware
        datetime is first parsed, then the tzinfo is stripped. This preserves
        the local time representation for display purposes.
    """
    # Normalize the timezone format for datetime.fromisoformat()
    # Jira uses +0000 format, but fromisoformat needs +00:00
    normalized = datetime_str
    if datetime_str.endswith("Z"):
        normalized = datetime_str[:-1] + "+00:00"
    elif len(datetime_str) >= 5:
        # Check for timezone offset without colon (e.g., +0000 or -0500)
        # This matches patterns like ...+0000 or ...-0500
        last5 = datetime_str[-5:]
        if (last5[0] in "+-") and last5[1:].isdigit():
            # Insert colon: +0000 -> +00:00
            normalized = datetime_str[:-2] + ":" + datetime_str[-2:]

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise ValueError(f"Cannot parse datetime string '{datetime_str}': {e}") from e

    # If the parsed datetime has no timezone info, apply the server timezone
    if parsed.tzinfo is None:
        tz = ZoneInfo(server_timezone)
        parsed = parsed.replace(tzinfo=tz)

    # Convert to naive datetime by stripping timezone info
    # This preserves the local time representation
    return parsed.replace(tzinfo=None)


def _get_total_logged_seconds(worklogs: list[JiraWorklogEntry]) -> int:
    """Sum total seconds logged across all worklogs."""
    return sum(w.time_spent_seconds for w in worklogs)


def _get_worker_logged_seconds(
    worklogs: list[JiraWorklogEntry],
) -> dict[str, int]:
    """Get total seconds logged per worker (by user_id)."""
    result: dict[str, int] = defaultdict(int)
    for w in worklogs:
        result[w.author.user_id] += w.time_spent_seconds
    return dict(result)


def get_earliest_worklog_time(
    worklogs: list[JiraWorklogEntry],
    server_timezone: str = "UTC",
) -> datetime:
    """Get the earliest worklog start time.

    Args:
        worklogs: Non-empty list of worklog entries
        server_timezone: Fallback timezone for datetime parsing

    Returns:
        Earliest start time as naive datetime

    Raises:
        ValueError: If worklogs is empty
    """
    if not worklogs:
        raise ValueError("worklogs list must not be empty")
    return min(parse_jira_datetime(w.started, server_timezone) for w in worklogs)


def get_latest_worklog_time(
    worklogs: list[JiraWorklogEntry],
    server_timezone: str = "UTC",
) -> datetime:
    """Get the latest worklog start time.

    Args:
        worklogs: Non-empty list of worklog entries
        server_timezone: Fallback timezone for datetime parsing

    Returns:
        Latest start time as naive datetime

    Raises:
        ValueError: If worklogs is empty
    """
    if not worklogs:
        raise ValueError("worklogs list must not be empty")
    return max(parse_jira_datetime(w.started, server_timezone) for w in worklogs)


def _get_assignee_worker_id(
    issue: JiraIssueResponse,
    worklogs: list[JiraWorklogEntry],
    workers: dict[str, WorkerId],
) -> WorkerId:
    """Determine the assigned worker ID for an issue.

    Priority:
    1. Use the issue's assignee if they're in the workers map
    2. Use the worker who logged the most time (if worklogs exist)
    3. Generate a new placeholder worker ID

    Args:
        issue: The Jira issue
        worklogs: List of worklog entries (may be empty)
        workers: Mapping from Jira user_id to WorkerId

    Returns:
        WorkerId for the assigned worker
    """
    # Try assignee first
    if issue.fields.assignee:
        assignee_id = issue.fields.assignee.user_id
        if assignee_id in workers:
            return workers[assignee_id]

    # Try worker with most logged time
    if worklogs:
        logged_by_worker = _get_worker_logged_seconds(worklogs)
        most_logged_id = max(logged_by_worker, key=lambda k: logged_by_worker[k])
        if most_logged_id in workers:
            return workers[most_logged_id]

    # Generate placeholder
    return generate_worker_id()


def _extract_not_started(
    issue: JiraIssueResponse,
    workers: dict[str, WorkerId],
) -> ExtractedCompletion:
    """Extract NotStartedCompletion for an issue with no worklogs and no resolution."""
    assignee_jira_id = issue.fields.assignee.user_id if issue.fields.assignee else None
    allowed_workers = (
        [workers[assignee_jira_id]]
        if assignee_jira_id and assignee_jira_id in workers
        else None
    )
    return ExtractedCompletion(
        completion=NotStartedCompletion(),
        allowed_workers=allowed_workers,
    )


def _extract_started(
    issue: JiraIssueResponse,
    worklogs: list[JiraWorklogEntry],
    workers: dict[str, WorkerId],
    server_timezone: str,
) -> ExtractedCompletion:
    """Extract StartedCompletion for an issue with worklogs but no resolution.

    Args:
        issue: The Jira issue
        worklogs: Non-empty list of worklog entries
        workers: Mapping from Jira user_id to WorkerId
        server_timezone: Fallback timezone for datetime parsing

    Returns:
        ExtractedCompletion with StartedCompletion
    """
    assigned_worker_id = _get_assignee_worker_id(issue, worklogs, workers)
    total_seconds = _get_total_logged_seconds(worklogs)
    hours_logged = total_seconds / 3600.0
    # worklogs is non-empty, so get_earliest_worklog_time won't raise
    start_time = get_earliest_worklog_time(worklogs, server_timezone)

    return ExtractedCompletion(
        completion=StartedCompletion(
            assignee=assigned_worker_id,
            start_time=start_time,
            hours_logged=hours_logged,
        ),
    )


def _extract_done_with_worklogs(
    issue: JiraIssueResponse,
    worklogs: list[JiraWorklogEntry],
    workers: dict[str, WorkerId],
    server_timezone: str,
) -> ExtractedCompletion:
    """Extract DoneCompletion for a resolved issue with worklogs.

    Args:
        issue: The Jira issue (must have resolution date)
        worklogs: Non-empty list of worklog entries
        workers: Mapping from Jira user_id to WorkerId
        server_timezone: Fallback timezone for datetime parsing

    Returns:
        ExtractedCompletion with DoneCompletion
    """
    assigned_worker_id = _get_assignee_worker_id(issue, worklogs, workers)
    total_seconds = _get_total_logged_seconds(worklogs)
    hours_logged = total_seconds / 3600.0

    # worklogs is non-empty, so these won't raise
    start_time = get_earliest_worklog_time(worklogs, server_timezone)
    end_time = get_latest_worklog_time(worklogs, server_timezone)

    # Ensure end_time > start_time (model validation requirement)
    if end_time <= start_time:
        end_time = start_time + timedelta(seconds=1)

    return ExtractedCompletion(
        completion=DoneCompletion(
            assignee=assigned_worker_id,
            start_time=start_time,
            hours_logged=hours_logged,
            end_time=end_time,
        ),
    )


def _extract_done_zero_work(
    resolution_date: str,
    server_timezone: str,
) -> ExtractedCompletion:
    """Extract DoneCompletion for a resolved issue with no worklogs.

    Args:
        resolution_date: The resolution date string (must not be None)
        server_timezone: Fallback timezone for datetime parsing

    Returns:
        ExtractedCompletion with DoneCompletion (epsilon hours)
    """
    resolution_datetime = parse_jira_datetime(resolution_date, server_timezone)
    # Generate placeholder worker for zero-work tasks
    assigned_worker_id = generate_worker_id()

    return ExtractedCompletion(
        completion=DoneCompletion(
            assignee=assigned_worker_id,
            start_time=resolution_datetime,
            hours_logged=EPSILON_HOURS,
            # end_time must be after start_time per model validation
            end_time=resolution_datetime + timedelta(seconds=1),
        ),
    )


def extract_completion(
    issue: JiraIssueResponse,
    workers: dict[str, WorkerId],
    server_timezone: str = "UTC",
) -> ExtractedCompletion:
    """Extract task completion status from a Jira issue.

    Args:
        issue: The Jira issue response
        workers: Mapping from Jira user_id to WorkerId
        server_timezone: IANA timezone name for parsing datetimes without
            timezone info (e.g., 'America/New_York'). Defaults to 'UTC'.

    Returns:
        ExtractedCompletion with completion status and optional allowed_workers

    Logic:
    - No worklogs + no resolution → NotStartedCompletion
    - Has worklogs + no resolution → StartedCompletion
    - Has resolution + has worklogs → DoneCompletion (uses worklog times)
    - Has resolution + no worklogs → DoneCompletion (uses resolution date)
    """
    worklogs = issue.fields.worklog.worklogs if issue.fields.worklog else []
    resolution_date = issue.fields.resolutiondate
    has_worklogs = len(worklogs) > 0
    is_resolved = resolution_date is not None

    # Exhaustive case analysis - every combination is handled
    if not is_resolved and not has_worklogs:
        logger.debug("Issue %s: not started (no worklogs, no resolution)", issue.key)
        return _extract_not_started(issue, workers)

    if not is_resolved and has_worklogs:
        logger.debug(
            "Issue %s: started (%d worklogs, no resolution)", issue.key, len(worklogs)
        )
        return _extract_started(issue, worklogs, workers, server_timezone)

    if is_resolved and has_worklogs:
        logger.debug(
            "Issue %s: done with worklogs (%d worklogs)", issue.key, len(worklogs)
        )
        return _extract_done_with_worklogs(issue, worklogs, workers, server_timezone)

    # is_resolved and not has_worklogs
    # Type narrowing: resolution_date is not None since is_resolved is True
    assert resolution_date is not None
    logger.debug("Issue %s: done without worklogs", issue.key)
    return _extract_done_zero_work(resolution_date, server_timezone)


# Dependency link type names that indicate "depends on" relationship
DEPENDS_ON_LINK_TYPES = {
    "Depends",
    "depends on",
    "Dependency",
    "Schedule after",
    "schedule after",
}

# Link types where the inward issue depends on this issue
BLOCKS_LINK_TYPES = {
    "Blocks",
    "blocks",
    "is blocked by",
}


def extract_dependencies(
    issue: JiraIssueResponse,
    task_map: dict[str, str],
    started_issues: set[str] | None = None,
) -> list[ExtractedDependency]:
    """Extract dependencies from a Jira issue's links.

    Args:
        issue: The Jira issue response
        task_map: Mapping from issue key to task ID
        started_issues: Set of issue keys that have been started (have worklogs)

    Returns:
        List of dependencies where this issue depends on another

    Rules:
    - "Depends" type outward link: this depends on target
    - "Blocks" type inward link: this depends on source
    - Skip if both issues have been started
    - Skip if target issue not in task_map
    """
    if started_issues is None:
        started_issues = set()

    dependencies: list[ExtractedDependency] = []
    issue_key = issue.key

    if not issue.fields.issuelinks:
        return dependencies

    for link in issue.fields.issuelinks:
        target_key: str | None = None

        # Check for "depends on" type links (outward)
        if link.link_type.name in DEPENDS_ON_LINK_TYPES and link.outward_issue:
            target_key = link.outward_issue.key

        # Check for "blocks" type links (inward means we depend on them)
        if link.link_type.name in BLOCKS_LINK_TYPES and link.inward_issue:
            target_key = link.inward_issue.key

        if target_key is None:
            continue

        # Skip if target not in our task map
        if target_key not in task_map:
            continue

        # Skip if both issues have been started
        if issue_key in started_issues and target_key in started_issues:
            continue

        dependencies.append(ExtractedDependency(target_key=target_key))

    return dependencies


# Link types indicating parent-child relationship
PARENT_OF_LINK_TYPES = {"Parent of", "parent of", "is parent of"}
CHILD_OF_LINK_TYPES = {"Child of", "child of", "is child of"}


def _is_parent_of_link(
    link_type_name: str | None, link_type_outward: str | None
) -> bool:
    """Check if a link represents a 'parent of' relationship.

    Jira link types have:
    - name: e.g., "Hierarchy", "Parent"
    - outward: e.g., "is parent of"
    - inward: e.g., "is child of"

    We check both name and outward fields to handle different Jira configurations.
    """
    if link_type_name and link_type_name in PARENT_OF_LINK_TYPES:
        return True
    return bool(link_type_outward and link_type_outward in PARENT_OF_LINK_TYPES)


def _is_child_of_link(link_type_name: str | None, link_type_inward: str | None) -> bool:
    """Check if a link represents a 'child of' relationship.

    Jira link types have:
    - name: e.g., "Hierarchy", "Parent"
    - outward: e.g., "is parent of"
    - inward: e.g., "is child of"

    We check both name and inward fields to handle different Jira configurations.
    """
    if link_type_name and link_type_name in CHILD_OF_LINK_TYPES:
        return True
    return bool(link_type_inward and link_type_inward in CHILD_OF_LINK_TYPES)


def build_hierarchy(
    issues: list[JiraIssueResponse],
) -> tuple[dict[str, HierarchyEntry], list[HierarchyWarning]]:
    """Build parent-child hierarchy from issues.

    Args:
        issues: List of Jira issue responses

    Returns:
        Tuple of (hierarchy dict, warnings list)

    Sources of hierarchy (in priority order):
    1. Parent field (standard Jira subtask relationship)
    2. Epic Link field (stories/tasks linked to epics)
    3. "Parent of" / "Child of" links
    """
    hierarchy: dict[str, HierarchyEntry] = {}
    warnings: list[HierarchyWarning] = []

    # Build issue type map for detecting sub-epics
    issue_types: dict[str, str] = {}
    for issue in issues:
        issue_types[issue.key] = issue.fields.issuetype.name

    # First pass: collect parent relationships from parent field and epic_link
    for issue in issues:
        # Priority: parent field > epic_link
        parent_key = issue.fields.parent.key if issue.fields.parent else None
        if parent_key is None and issue.fields.epic_link:
            parent_key = issue.fields.epic_link

        hierarchy[issue.key] = HierarchyEntry(
            issue_key=issue.key,
            parent_key=parent_key,
        )

        # Check for sub-epic (epic with epic parent)
        if parent_key and issue.fields.issuetype.name.lower() == "epic":
            parent_type = issue_types.get(parent_key, "")
            if parent_type.lower() == "epic":
                msg = f"Sub-epic detected: {issue.key} has epic parent {parent_key}"
                warnings.append(HierarchyWarning(issue_key=issue.key, message=msg))

    # Second pass: look for "Parent of" / "Child of" links
    for issue in issues:
        if not issue.fields.issuelinks:
            continue

        for link in issue.fields.issuelinks:
            # "Parent of" outward link: this issue is parent of the linked issue
            if (
                _is_parent_of_link(link.link_type.name, link.link_type.outward)
                and link.outward_issue
            ):
                child_key = link.outward_issue.key
                # Only set if no parent already defined
                if child_key in hierarchy and hierarchy[child_key].parent_key is None:
                    hierarchy[child_key].parent_key = issue.key

            # "Child of" inward link: the linked issue is parent of this issue
            if (
                _is_child_of_link(link.link_type.name, link.link_type.inward)
                and link.inward_issue
                and hierarchy[issue.key].parent_key is None
            ):
                hierarchy[issue.key].parent_key = link.inward_issue.key

    logger.debug(
        "Built hierarchy: %d entries, %d warnings", len(hierarchy), len(warnings)
    )
    return hierarchy, warnings


def extract_workers_with_no_hours(
    issues: list[JiraIssueResponse],
) -> dict[str, Worker]:
    """Extract workers from issues (from worklogs and assignees) with
    no average hours statistic

    Args:
        issues: List of Jira issue responses

    Returns:
        Dict mapping Jira user_id to Worker objects
    """
    logger.debug("Extracting workers from %d issues", len(issues))
    workers: dict[str, Worker] = {}

    for issue in issues:
        # Extract from assignee
        if issue.fields.assignee:
            user_id = issue.fields.assignee.user_id
            if user_id not in workers:
                workers[user_id] = Worker(
                    id=generate_worker_id(),
                    name=issue.fields.assignee.display_name,
                    jira_user_id=user_id,
                    hours_per_workday=8.0,  # Default, will be calculated later
                )

        # Extract from worklogs
        if issue.fields.worklog:
            for worklog in issue.fields.worklog.worklogs:
                user_id = worklog.author.user_id
                if user_id not in workers:
                    workers[user_id] = Worker(
                        id=generate_worker_id(),
                        name=worklog.author.display_name,
                        jira_user_id=user_id,
                        hours_per_workday=8.0,  # Default
                    )

    logger.debug("Extracted %d workers", len(workers))
    return workers


def calculate_hours_per_workday(
    jira_user_id: str,
    worklogs: list[JiraWorklogEntry],
) -> float | None:
    """Calculate average hours per workday for a worker.

    Args:
        jira_user_id: The Jira user identifier (name for Data Center,
            accountId for Cloud)
        worklogs: All worklogs to analyze

    Returns:
        Average hours per workday, or None if no worklogs for this user
    """
    # Filter worklogs for this user
    user_worklogs = [w for w in worklogs if w.author.user_id == jira_user_id]
    if not user_worklogs:
        return None

    # Group by date - each worklog has a date, so hours_by_date will be non-empty
    hours_by_date: dict[str, float] = defaultdict(float)
    for w in user_worklogs:
        # Extract just the date part
        date_str = w.started.split("T")[0]
        hours_by_date[date_str] += w.time_spent_seconds / 3600.0

    # Return average (hours_by_date is non-empty since user_worklogs is non-empty)
    return sum(hours_by_date.values()) / len(hours_by_date)


def extract_task(
    issue: JiraIssueResponse,
    workers: dict[str, WorkerId],
    server_url: str,
    parent_id: TaskId | None = None,
    server_timezone: str = "UTC",
) -> Task:
    """Extract a Fluxx Task from a Jira issue.

    Args:
        issue: The Jira issue response
        workers: Mapping from Jira account_id to WorkerId
        server_url: The Jira server URL
        parent_id: Optional parent task ID
        server_timezone: IANA timezone name for parsing datetimes without
            timezone info. Defaults to 'UTC'.

    Returns:
        A Task object with Jira data populated
    """
    # Parse the issue key
    issue_key = JiraIssueKey.from_string(issue.key)

    # Create Jira reference
    jira_ref = JiraReference(
        server_url=server_url,
        issue_key=issue_key,
    )

    # Create duration distribution from Jira fields
    original_estimate = None
    remaining_estimate = None
    story_points = issue.fields.story_points

    if issue.fields.timetracking:
        original_estimate = issue.fields.timetracking.original_estimate_seconds
        remaining_estimate = issue.fields.timetracking.remaining_estimate_seconds

    duration_dist = JiraDurationDistribution(
        original_estimate_seconds=original_estimate,
        story_points=story_points,
        remaining_estimate_seconds=remaining_estimate,
    )

    # Extract completion status
    completion_result = extract_completion(issue, workers, server_timezone)

    # Build the task
    task = Task(
        id=generate_task_id(),
        title=issue.fields.summary,
        description=issue.fields.description or "",
        jira_reference=jira_ref,
        jira_issue_type=issue.fields.issuetype.name,
        duration_distribution=duration_dist,
        completion=completion_result.completion,
        parent_id=parent_id,
        allowed_workers=completion_result.allowed_workers,
    )

    logger.debug(
        "Extracted task %s from issue %s: type=%s, completion=%s",
        task.id,
        issue.key,
        issue.fields.issuetype.name,
        type(completion_result.completion).__name__,
    )
    return task
