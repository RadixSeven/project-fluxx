"""Jira import orchestration for Project Fluxx.

This module provides the high-level orchestration for importing Jira projects
into Fluxx, coordinating the client, extraction, and distribution fitting
components.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from fluxx.data.id_generation import generate_dag_id, generate_dag_version_id
from fluxx.data.models import (
    DAG,
    BranchId,
    ConstraintType,
    Dependency,
    DoneCompletion,
    Endpoint,
    JiraDurationDistribution,
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    ShiftedLognormal,
    Task,
    TaskId,
    Worker,
    WorkerId,
)
from fluxx.jira.api_types import JiraIssueResponse, JiraWorklogEntry
from fluxx.jira.client import JiraClient
from fluxx.jira.distributions import (
    EstimateBin,
    create_estimate_bins,
    find_bin_for_estimate,
    fit_fallback_distribution,
)
from fluxx.jira.extraction import (
    build_hierarchy,
    calculate_hours_per_workday,
    extract_completion,
    extract_dependencies,
    extract_task,
    extract_workers_with_no_hours,
)
from fluxx.jira.models import JiraConfig, JiraDurationHistoryEntry, JiraIssueKey


@dataclass
class ImportProgress:
    """Progress information during Jira import."""

    total_issues: int = 0
    processed_issues: int = 0
    current_phase: str = "initializing"


@dataclass
class ImportWarningFluxx:
    """Warning generated during import.

    The Fluxx suffix distinguishes it from the builtin ImportWarning
    """

    issue_key: str
    message: str


@dataclass
class ImportResult:
    """Result of a Jira import operation."""

    project: Project
    warnings: list[ImportWarningFluxx] = field(default_factory=list)
    history_entries: list[JiraDurationHistoryEntry] = field(default_factory=list)


# Required fields for Jira API requests
REQUIRED_FIELDS = [
    "summary",
    "description",
    "issuetype",
    "status",
    "assignee",
    "parent",
    "issuelinks",
    "resolutiondate",
    "worklog",
    "timetracking",
    "customfield_10016",  # Story points (common custom field ID)
]


def _collect_all_worklogs(issues: list[JiraIssueResponse]) -> list[JiraWorklogEntry]:
    """Collect all worklogs from a list of issues."""
    worklogs: list[JiraWorklogEntry] = []
    for issue in issues:
        if issue.fields.worklog:
            worklogs.extend(issue.fields.worklog.worklogs)
    return worklogs


def _create_history_entries(
    issues: list[JiraIssueResponse],
    workers: dict[str, Worker],
    server_url: str,
    server_timezone: str,
) -> list[JiraDurationHistoryEntry]:
    """Create history entries from completed issues.

    Only issues with DoneCompletion are included.

    Args:
        issues: All imported issues
        workers: Worker map from Jira account ID to Worker
        server_url: Jira server URL
        server_timezone: Server timezone for datetime parsing

    Returns:
        List of history entries for completed issues
    """
    entries: list[JiraDurationHistoryEntry] = []

    for issue in issues:
        # Extract completion to determine if done
        workers_by_id: dict[str, WorkerId] = {}
        for jira_id, w in workers.items():
            if w.jira_account_id:
                workers_by_id[jira_id] = w.id

        completion_result = extract_completion(issue, workers_by_id, server_timezone)

        # Only include completed issues
        if not isinstance(completion_result.completion, DoneCompletion):
            continue

        # Get original estimate
        original_estimate = None
        if issue.fields.timetracking:
            original_estimate = issue.fields.timetracking.original_estimate_seconds

        # Calculate total logged time
        worklogs = issue.fields.worklog.worklogs if issue.fields.worklog else []
        total_seconds = (
            sum(w.time_spent_seconds for w in worklogs) if len(worklogs) > 0 else None
        )

        # Determine the primary worker (the one who logged most time)
        worker_jira_id: str | None = None
        if worklogs:
            logged_by_worker: dict[str, int] = defaultdict(int)
            for wlog in worklogs:
                logged_by_worker[wlog.author.account_id] += wlog.time_spent_seconds
            worker_jira_id = max(logged_by_worker, key=lambda k: logged_by_worker[k])

        entries.append(
            JiraDurationHistoryEntry(
                server_url=server_url,
                issue_key=JiraIssueKey.from_string(issue.key),
                original_estimate_seconds=original_estimate,
                worker_jira_id=worker_jira_id,
                issue_type=issue.fields.issuetype.name,
                total_logged_time_seconds=total_seconds,
            )
        )

    return entries


def _build_duration_distribution(
    issue: JiraIssueResponse,
    bins: list[EstimateBin],
    fallback: ShiftedLognormal | None,
) -> JiraDurationDistribution | ShiftedLognormal:
    """Build duration distribution for an issue.

    Args:
        issue: The Jira issue
        bins: Estimate bins for conditional distributions
        fallback: Fallback distribution when no estimate available

    Returns:
        JiraDurationDistribution if issue has Jira estimate data,
        or ShiftedLognormal from fitted distributions
    """
    # Get original estimate in seconds
    original_estimate_seconds: int | None = None
    remaining_estimate_seconds: int | None = None
    story_points = issue.fields.story_points

    if issue.fields.timetracking:
        original_estimate_seconds = issue.fields.timetracking.original_estimate_seconds
        remaining_estimate_seconds = (
            issue.fields.timetracking.remaining_estimate_seconds
        )

    # If we have bins and an estimate, use the bin distribution
    if bins and original_estimate_seconds:
        # Convert to hours for bin lookup
        estimate_hours = original_estimate_seconds / 3600.0
        bin_ = find_bin_for_estimate(estimate_hours, bins)
        return bin_.distribution

    # If we have a fallback distribution, use it
    if fallback:
        return fallback

    # Return Jira distribution data (which needs to be resolved later)
    return JiraDurationDistribution(
        original_estimate_seconds=original_estimate_seconds,
        story_points=story_points,
        remaining_estimate_seconds=remaining_estimate_seconds,
    )


def _build_project(
    issues: list[JiraIssueResponse],
    workers: dict[str, Worker],
    config: JiraConfig,
    bins: list[EstimateBin],
    fallback: ShiftedLognormal | None,
    project_name: str,
) -> tuple[Project, list[ImportWarningFluxx]]:
    """Build a Project from extracted Jira data.

    Args:
        issues: All Jira issues to import
        workers: Extracted workers keyed by Jira account ID
        config: Jira configuration
        bins: Estimate bins for duration distributions
        fallback: Fallback distribution
        project_name: Name for the project

    Returns:
        Tuple of (Project, list of warnings)
    """
    warnings: list[ImportWarningFluxx] = []

    # Build hierarchy
    hierarchy, hierarchy_warnings = build_hierarchy(issues)
    for hw in hierarchy_warnings:
        warnings.append(ImportWarningFluxx(issue_key=hw.issue_key, message=hw.message))

    # Create mapping from Jira account ID to WorkerId
    workers_by_jira_id: dict[str, WorkerId] = {}
    for w in workers.values():
        if w.jira_account_id:
            workers_by_jira_id[w.jira_account_id] = w.id

    # First pass: create tasks (without parent relationships or dependencies)
    task_by_key: dict[str, Task] = {}
    for issue in issues:
        task = extract_task(
            issue=issue,
            workers=workers_by_jira_id,
            server_url=config.server_url,
            parent_id=None,  # Set in second pass
            server_timezone=config.server_timezone,
        )

        # Override duration distribution with fitted distribution if available
        dist = _build_duration_distribution(issue, bins, fallback)
        task = task.model_copy(update={"duration_distribution": dist})

        task_by_key[issue.key] = task

    # Second pass: set parent relationships
    for issue_key, entry in hierarchy.items():
        if entry.parent_key and entry.parent_key in task_by_key:
            parent_id = task_by_key[entry.parent_key].id
            task = task_by_key[issue_key]
            task_by_key[issue_key] = task.model_copy(update={"parent_id": parent_id})

    # Third pass: extract and add dependencies to tasks
    started_issues = {
        issue.key
        for issue in issues
        if issue.fields.worklog and issue.fields.worklog.worklogs
    }

    for issue in issues:
        deps = extract_dependencies(
            issue=issue,
            task_map={k: str(v.id) for k, v in task_by_key.items()},
            started_issues=started_issues,
        )

        if deps:
            task = task_by_key[issue.key]
            new_dependencies: list[Dependency] = list(task.dependencies)

            for dep in deps:
                target_task = task_by_key.get(dep.target_key)
                if target_task:
                    # Create dependency: this task's start >= target's end
                    new_dependencies.append(
                        Dependency(
                            source_endpoint=Endpoint.START,
                            target_node_id=target_task.id,
                            target_endpoint=Endpoint.END,
                            constraint_type=ConstraintType.GREATER_EQUAL,
                        )
                    )

            task_by_key[issue.key] = task.model_copy(
                update={"dependencies": new_dependencies}
            )

    # Build persistent objects and DAG
    dag_id = generate_dag_id()
    dag_version_id = generate_dag_version_id()

    persistent_tasks: dict[PersistentObjectId, PersistentTask] = {}
    node_map: dict[TaskId | BranchId, PersistentObjectId] = {}

    for task in task_by_key.values():
        persistent_id = PersistentObjectId(str(task.id))
        persistent_tasks[persistent_id] = PersistentTask(
            id=persistent_id,
            versions={dag_version_id: task},
        )
        node_map[task.id] = persistent_id

    persistent_branches: dict[PersistentObjectId, PersistentBranch] = {}

    # Build DAG
    dag = DAG(
        id=dag_id,
        current_version_id=dag_version_id,
        node_map=node_map,
    )

    # Build project
    now = datetime.now().astimezone()
    project = Project(
        version="1.2",
        metadata=ProjectMetadata(
            name=project_name,
            created=now,
            last_modified=now,
        ),
        workers=list(workers.values()),
        dag=dag,
        persistent_tasks=persistent_tasks,
        persistent_branches=persistent_branches,
        history_events=[],
        current_event_id=None,
        simulations=[],
    )

    return project, warnings


def generate_progress_updater(
    progress_callback: Callable[[ImportProgress], None] | None = None,
) -> Callable[[str, int, int], None]:
    """Return a progress updater closure that calls ``progress_callback``

    The signature of the updater is:

    def update_progress(phase: str, processed, total) -> None

    Args:
        progress_callback: Progress callback

    Returns:
         a progress updater closure that calls ``progress_callback``
    """

    def update_progress(phase: str, processed: int, total: int) -> None:
        if progress_callback:
            progress_callback(
                ImportProgress(
                    total_issues=total,
                    processed_issues=processed,
                    current_phase=phase,
                )
            )

    return update_progress


def import_from_jira(
    client: JiraClient,
    jql: str,
    config: JiraConfig,
    project_name: str,
    min_samples_for_bins: int = 30,
    progress_callback: Callable[[ImportProgress], None] | None = None,
) -> ImportResult:
    """Import issues from Jira and create a Fluxx project.

    Args:
        client: Configured Jira client
        jql: JQL query to select issues to import
        config: Jira server configuration
        project_name: Name for the new project
        min_samples_for_bins: Minimum samples per distribution bin
        progress_callback: Optional callback for progress updates

    Returns:
        ImportResult with the created project and any warnings

    Raises:
        InsufficientDataError if no worklog has logged time
    """
    update_progress = generate_progress_updater(progress_callback)

    update_progress("fetching_issues", 0, 0)

    # Fetch all issues
    issues: list[JiraIssueResponse] = []
    for issue_dict in client.search(jql, REQUIRED_FIELDS, expand=["changelog"]):
        issues.append(JiraIssueResponse.model_validate(issue_dict))

    update_progress("extracting_workers", 0, len(issues))

    workers = extract_workers(issues)

    update_progress("building_history", len(issues) // 2, len(issues))

    # Create history entries for distribution fitting
    history_entries = _create_history_entries(
        issues, workers, config.server_url, config.server_timezone
    )

    # Build duration distributions from history
    bins: list[EstimateBin] = []

    # Prepare data for distribution fitting
    # (estimate_hours, actual_hours) tuples
    estimate_data: list[tuple[float, float]] = []
    actual_times: list[float] = []

    for entry in history_entries:
        # History entries are only created with positive logged time (>EPSILON_HOURS),
        # so total_logged_time_seconds is always positive here. The check
        # satisfies mypy's type narrowing.
        if entry.total_logged_time_seconds is None:
            continue
        actual_hours = entry.total_logged_time_seconds / 3600.0
        actual_times.append(actual_hours)

        if entry.original_estimate_seconds:
            estimate_hours = entry.original_estimate_seconds / 3600.0
            estimate_data.append((estimate_hours, actual_hours))

    update_progress("fitting_distributions", len(issues) * 3 // 4, len(issues))

    # Fit distributions
    # actual_times is always non-empty when we call fit_fallback_distribution
    # because history_entries only includes completed issues with logged time
    fallback: ShiftedLognormal | None = None
    if actual_times:
        fallback = fit_fallback_distribution(actual_times)

    if estimate_data and len(estimate_data) >= min_samples_for_bins:
        bins = create_estimate_bins(estimate_data, min_samples=min_samples_for_bins)

    update_progress("building_project", len(issues), len(issues))

    # Build the project
    project, warnings = _build_project(
        issues=issues,
        workers=workers,
        config=config,
        bins=bins,
        fallback=fallback,
        project_name=project_name,
    )

    return ImportResult(
        project=project,
        warnings=warnings,
        history_entries=history_entries,
    )


def extract_workers(issues: list[JiraIssueResponse]) -> dict[str, Worker]:
    """Extract workers from Jira issues.

    Args:
        issues: Jira issues to extract workers from

    Returns:
        mapping from jira_id (for the worker) to worker
    """
    workers = extract_workers_with_no_hours(issues)

    # Calculate hours per workday for each worker
    all_worklogs = _collect_all_worklogs(issues)
    for jira_id, worker in workers.items():
        avg_hours = calculate_hours_per_workday(jira_id, all_worklogs)
        if avg_hours is not None:
            workers[jira_id] = worker.model_copy(
                update={"hours_per_workday": avg_hours}
            )
    return workers


def fetch_and_validate_issues(
    client: JiraClient,
    jql: str,
) -> tuple[list[JiraIssueResponse], list[ImportWarningFluxx]]:
    """Fetch issues from Jira and validate them.

    This is a lower-level function for fetching issues without
    building a complete project.

    Args:
        client: Configured Jira client
        jql: JQL query to select issues

    Returns:
        Tuple of (issues, warnings)
    """
    warnings: list[ImportWarningFluxx] = []
    issues: list[JiraIssueResponse] = []

    for issue_dict in client.search(jql, REQUIRED_FIELDS, expand=["changelog"]):
        try:
            issue = JiraIssueResponse.model_validate(issue_dict)
            issues.append(issue)
        except Exception as e:
            key = issue_dict.get("key", "unknown")
            if isinstance(key, str):
                warnings.append(
                    ImportWarningFluxx(issue_key=key, message=f"Validation error: {e}")
                )
            else:
                warnings.append(
                    ImportWarningFluxx(
                        issue_key="unknown", message=f"Validation error: {e}"
                    )
                )

    return issues, warnings
