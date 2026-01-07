"""Jira import orchestration for Project Fluxx.

This module provides the high-level orchestration for importing Jira projects
into Fluxx, coordinating the client, extraction, and distribution fitting
components.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from fluxx.data.id_generation import (
    generate_dag_id,
    generate_dag_version_id,
    generate_event_id,
)
from fluxx.data.models import (
    DAG,
    BranchId,
    ConstraintType,
    DAGEvent,
    DAGVersionId,
    Dependency,
    DoneCompletion,
    Endpoint,
    EventType,
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
    HierarchyEntry,
    _is_child_of_link,
    _is_parent_of_link,
    build_hierarchy,
    calculate_hours_per_workday,
    extract_completion,
    extract_dependencies,
    extract_task,
    extract_workers_with_no_hours,
)
from fluxx.jira.models import (
    JiraConfig,
    JiraDurationHistoryEntry,
    JiraIssueKey,
)


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


@dataclass
class SyncResult:
    """Result of a Jira sync operation."""

    project: Project
    updated_count: int = 0
    created_count: int = 0
    deleted_keys: list[str] = field(default_factory=list)
    warnings: list[ImportWarningFluxx] = field(default_factory=list)


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
    "customfield_10473",  # Story points
    "customfield_12202",  # Epic Link field
]


def get_children_from_links(
    issues: list[JiraIssueResponse],
    already_fetched: set[str],
) -> set[str]:
    """Extract child issue keys from "parent of"/"child of" links.

    Args:
        issues: List of Jira issues to examine
        already_fetched: Set of issue keys already fetched (to exclude)

    Returns:
        Set of issue keys that are children according to links but not yet fetched
    """
    child_keys: set[str] = set()

    for issue in issues:
        if not issue.fields.issuelinks:
            continue

        for link in issue.fields.issuelinks:
            # "parent of" outward link: linked issue is a child of this issue
            if (
                _is_parent_of_link(link.link_type.name, link.link_type.outward)
                and link.outward_issue
            ):
                child_key = link.outward_issue.key
                if child_key not in already_fetched:
                    child_keys.add(child_key)

            # "child of" inward link: linked issue is also a child
            # (the inward issue claims to be a child of something,
            # but we see it from the parent's perspective)
            # Actually, "child of" inward means: the inward_issue is saying
            # "I am child of this issue" - so inward_issue is a child
            if (
                _is_child_of_link(link.link_type.name, link.link_type.inward)
                and link.inward_issue
            ):
                child_key = link.inward_issue.key
                if child_key not in already_fetched:
                    child_keys.add(child_key)

    return child_keys


def build_children_jql(parent_keys: list[str]) -> str:
    """Build JQL to fetch children of the given parent issues.

    Args:
        parent_keys: List of parent issue keys

    Returns:
        JQL query string to fetch all children via Epic Link or parent field
    """
    # Quote keys in case they have special characters
    quoted_keys = [f'"{key}"' for key in parent_keys]
    keys_list = ", ".join(quoted_keys)

    # Use both Epic Link and parent fields to catch all children
    return f'"Epic Link" in ({keys_list}) OR parent in ({keys_list})'


def fetch_all_issues_with_children(
    client: JiraClient,
    initial_jql: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[JiraIssueResponse]:
    """Fetch issues matching JQL and all their descendants.

    Uses a queue-based iterative approach to fetch all children:
    1. Fetch initial issues from JQL
    2. For each batch of issues, fetch their children via Epic Link/parent
    3. Check links for "parent of"/"child of" references
    4. Repeat until no new issues found

    Args:
        client: Jira client
        initial_jql: Initial JQL query
        progress_callback: Optional callback(phase, processed, total)

    Returns:
        List of all fetched issues (deduplicated by key)
    """
    if progress_callback:
        progress_callback("fetching_issues", 0, 0)

    # Track all fetched issues by key (for deduplication)
    issues_by_key: dict[str, JiraIssueResponse] = {}

    # Track which issues we've already fetched children for
    children_fetched_for: set[str] = set()

    # Fetch initial issues
    for issue_dict in client.search(initial_jql, REQUIRED_FIELDS, expand=["changelog"]):
        issue = JiraIssueResponse.model_validate(issue_dict)
        issues_by_key[issue.key] = issue

    if progress_callback:
        progress_callback("fetching_children", 0, len(issues_by_key))

    # Iteratively fetch children until no new issues found
    iteration = 0
    max_iterations = 100  # Safety limit to prevent infinite loops

    while iteration < max_iterations:
        iteration += 1

        # Find issues that need their children fetched
        need_children = [
            key for key in issues_by_key if key not in children_fetched_for
        ]

        if not need_children:
            break

        # Mark these as "children fetched" before querying
        # (to avoid re-fetching if the same keys appear again)
        for key in need_children:
            children_fetched_for.add(key)

        # Build JQL to fetch children of all pending issues
        children_jql = build_children_jql(need_children)

        # Fetch children
        new_issues_count = 0
        for issue_dict in client.search(
            children_jql, REQUIRED_FIELDS, expand=["changelog"]
        ):
            issue = JiraIssueResponse.model_validate(issue_dict)
            if issue.key not in issues_by_key:
                issues_by_key[issue.key] = issue
                new_issues_count += 1

        if progress_callback:
            progress_callback(
                "fetching_children", len(issues_by_key), len(issues_by_key)
            )

        # Check for children referenced in links but not yet fetched
        link_children = get_children_from_links(
            list(issues_by_key.values()), set(issues_by_key.keys())
        )

        # Fetch any link-referenced children individually
        for child_key in link_children:
            if child_key not in issues_by_key:
                try:
                    issue_dict = client.get_issue(
                        child_key, REQUIRED_FIELDS, expand=["changelog"]
                    )
                    issue = JiraIssueResponse.model_validate(issue_dict)
                    issues_by_key[issue.key] = issue
                except Exception:
                    # Issue might not exist or not accessible - skip it
                    pass

        # If no new issues were added (from JQL or links), we're done
        if new_issues_count == 0 and len(link_children) == 0:
            break

    return list(issues_by_key.values())


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
        workers: Worker map from Jira user_id to Worker
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
            if w.jira_user_id:
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
                logged_by_worker[wlog.author.user_id] += wlog.time_spent_seconds
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

    # Create mapping from Jira user_id to WorkerId
    workers_by_jira_id: dict[str, WorkerId] = {}
    for w in workers.values():
        if w.jira_user_id:
            workers_by_jira_id[w.jira_user_id] = w.id

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

    # Second pass: set parent relationships with children list and dependencies
    # Build parent-to-children mapping first
    parent_to_children: dict[str, list[str]] = {}
    for issue_key, entry in hierarchy.items():
        if entry.parent_key and entry.parent_key in task_by_key:
            if entry.parent_key not in parent_to_children:
                parent_to_children[entry.parent_key] = []
            parent_to_children[entry.parent_key].append(issue_key)

    # Update child tasks: set parent_id and add child.start >= parent.start dependency
    for issue_key, entry in hierarchy.items():
        if entry.parent_key and entry.parent_key in task_by_key:
            parent_task = task_by_key[entry.parent_key]
            child_task = task_by_key[issue_key]

            # Add dependency: child.start >= parent.start
            child_deps = list(child_task.dependencies)
            child_deps.append(
                Dependency(
                    source_endpoint=Endpoint.START,
                    target_node_id=parent_task.id,
                    target_endpoint=Endpoint.START,
                    constraint_type=ConstraintType.GREATER_EQUAL,
                )
            )

            task_by_key[issue_key] = child_task.model_copy(
                update={
                    "parent_id": parent_task.id,
                    "dependencies": child_deps,
                }
            )

    # Update parent tasks: add children list and parent.end >= child.end dependencies
    for parent_key, child_keys in parent_to_children.items():
        parent_task = task_by_key[parent_key]
        child_ids = [task_by_key[ck].id for ck in child_keys]

        # Add dependency for each child: parent.end >= child.end
        parent_deps = list(parent_task.dependencies)
        for child_id in child_ids:
            parent_deps.append(
                Dependency(
                    source_endpoint=Endpoint.END,
                    target_node_id=child_id,
                    target_endpoint=Endpoint.END,
                    constraint_type=ConstraintType.GREATER_EQUAL,
                )
            )

        task_by_key[parent_key] = parent_task.model_copy(
            update={
                "children": list(parent_task.children) + child_ids,
                "dependencies": parent_deps,
            }
        )

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
        version="1.3",
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

    # Fetch all issues including children recursively
    issues = fetch_all_issues_with_children(client, jql, update_progress)

    update_progress("extracting_workers", 0, len(issues))

    workers = extract_workers(issues)

    update_progress("building_history", len(issues) // 2, len(issues))

    # Create history entries for distribution fitting
    history_entries = _create_history_entries(
        issues, workers, config.server_url, config.server_timezone
    )

    # Prepare data for distribution fitting
    # (estimate_hours, actual_hours) tuples
    raw_estimate_data = extract_raw_estimate_data(history_entries)

    # Filter out the None values to accomodate our simple estimation methods
    actual_times: list[float] = [h for _, h in raw_estimate_data if h is not None]
    estimate_data: list[tuple[float, float]] = [
        (e, a) for e, a in raw_estimate_data if e is not None and a is not None
    ]

    update_progress("fitting_distributions", len(issues) * 3 // 4, len(issues))

    # Build duration distributions from history

    # Fit distributions
    # actual_times is always non-empty when we call fit_fallback_distribution
    # because history_entries only includes completed issues with logged time
    fallback: ShiftedLognormal | None = None
    if actual_times:
        fallback = fit_fallback_distribution(actual_times)

    bins: list[EstimateBin] = []
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


def extract_raw_estimate_data(
    history_entries: list[JiraDurationHistoryEntry],
) -> list[tuple[float | None, float | None]]:
    """Return the (estimated, actual) hours pairs from history entries.

    Since history entries can lack both total_logged_time_seconds (actual)
    and original_estimate_seconds (estimated), this estimate data has None
    values. Some fragile estimators cannot handle that and need more processing,
    thus this is "raw" estimate data.

    Args:
        history_entries: History entries

    Returns:
        the (estimated, actual) hours pairs
    """
    raw_estimate_data: list[tuple[float | None, float | None]] = []

    for entry in history_entries:
        if entry.total_logged_time_seconds is not None:
            actual_hours = entry.total_logged_time_seconds / 3600.0
        else:
            actual_hours = None

        if entry.original_estimate_seconds:
            estimate_hours = entry.original_estimate_seconds / 3600.0
        else:
            estimate_hours = None
        raw_estimate_data.append((estimate_hours, actual_hours))
    return raw_estimate_data


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


def collect_jira_referenced_tasks(
    project: Project,
) -> dict[str, dict[str, tuple[TaskId, Task]]]:
    """Collect all tasks with Jira references, grouped by server URL.

    Args:
        project: The project to scan

    Returns:
        Dict mapping server_url -> issue_key -> (task_id, task)
    """
    result: dict[str, dict[str, tuple[TaskId, Task]]] = defaultdict(dict)
    dag_version = project.dag.current_version_id

    for node_id, persistent_id in project.dag.node_map.items():
        if persistent_id not in project.persistent_tasks:
            continue

        ptask = project.persistent_tasks[persistent_id]
        task = ptask.versions.get(dag_version)
        if task is None:
            continue

        if task.jira_reference is None:
            continue

        server_url = task.jira_reference.server_url
        issue_key = str(task.jira_reference.issue_key)
        # node_id is actually TaskId since we checked it's in persistent_tasks
        task_id = TaskId(str(node_id))
        result[server_url][issue_key] = (task_id, task)

    return dict(result)


def build_sync_jql(issue_keys: list[str]) -> str:
    """Build JQL to fetch specific issues by key.

    Args:
        issue_keys: List of issue keys to fetch

    Returns:
        JQL query string
    """
    quoted_keys = [f'"{key}"' for key in issue_keys]
    return f"key in ({', '.join(quoted_keys)})"


def collect_jira_project_keys(project: Project) -> set[str]:
    """Collect all distinct Jira project keys from tasks with jira_reference.

    This iterates over all tasks with `jira_reference` and extracts their
    `project_key` values. Per spec section 11.3.4, this is effectively instant
    even for large files (<100K issues).

    Args:
        project: The project to scan

    Returns:
        Set of unique Jira project keys (e.g., {"CORE", "FHIR"})
    """
    project_keys: set[str] = set()
    dag_version = project.dag.current_version_id

    for persistent_id in project.dag.node_map.values():
        if persistent_id not in project.persistent_tasks:
            continue

        ptask = project.persistent_tasks[persistent_id]
        task = ptask.versions.get(dag_version)
        if task is None:
            continue

        if task.jira_reference is None:
            continue

        project_keys.add(task.jira_reference.issue_key.project_key)

    return project_keys


# Resolution values that indicate a completed issue (from spec section 11.4.3)
COMPLETED_RESOLUTIONS = ["Complete", "Fixed", "Not a bug", "Done", "Cannot Reproduce"]


def build_history_jql(
    project_keys: set[str],
    last_sync: datetime | None = None,
) -> str:
    """Build JQL query to fetch completed issues for history data.

    Args:
        project_keys: Set of Jira project keys to query
        last_sync: If provided, only fetch issues updated since this timestamp.
            If None, fetches all completed issues (first sync).

    Returns:
        JQL query string for completed issues

    Raises:
        ValueError: If project_keys is empty
    """
    if not project_keys:
        raise ValueError("project_keys cannot be empty")

    # Build project clause
    quoted_keys = [f'"{key}"' for key in sorted(project_keys)]
    project_clause = f"project in ({', '.join(quoted_keys)})"

    # Build resolution clause
    quoted_resolutions = [f'"{r}"' for r in COMPLETED_RESOLUTIONS]
    resolution_clause = f"resolution in ({', '.join(quoted_resolutions)})"

    # Combine clauses
    jql = f"{project_clause} AND {resolution_clause}"

    # Add date filter for incremental sync
    if last_sync is not None:
        # Format: "2024-01-15 14:30"
        date_str = last_sync.strftime("%Y-%m-%d %H:%M")
        jql += f' AND updated >= "{date_str}"'

    return jql


def fetch_history_entries(
    client: JiraClient,
    project_keys: set[str],
    last_sync: datetime | None,
    server_url: str,
    server_timezone: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[JiraDurationHistoryEntry]:
    """Fetch completed issues from Jira and create history entries.

    This queries all completed issues in the specified projects (optionally
    filtered by update date for incremental sync) and creates history entries
    for duration distribution fitting.

    Args:
        client: Configured Jira client
        project_keys: Set of Jira project keys to query
        last_sync: If provided, only fetch issues updated since this timestamp
        server_url: Jira server URL for history entries
        server_timezone: Server timezone for datetime parsing
        progress_callback: Optional callback(phase, processed, total)

    Returns:
        List of history entries for completed issues
    """
    if not project_keys:
        return []

    if progress_callback:
        progress_callback("fetching_history", 0, 0)

    # Build JQL for completed issues
    jql = build_history_jql(project_keys, last_sync)

    # Fields needed for history entries (minimal set)
    history_fields = [
        "summary",
        "issuetype",
        "status",
        "resolutiondate",
        "worklog",
        "timetracking",
    ]

    # Fetch issues
    issues: list[JiraIssueResponse] = []
    for issue_dict in client.search(jql, history_fields):
        try:
            issue = JiraIssueResponse.model_validate(issue_dict)
            issues.append(issue)
        except Exception:
            # Skip issues that fail validation (might be old/corrupt)
            pass

    if progress_callback:
        progress_callback("processing_history", len(issues), len(issues))

    # Create history entries (reuse existing function with empty workers)
    # Note: _create_history_entries only includes DoneCompletion issues
    return _create_history_entries(issues, {}, server_url, server_timezone)


def merge_history_entries(
    existing: list[JiraDurationHistoryEntry],
    new: list[JiraDurationHistoryEntry],
) -> list[JiraDurationHistoryEntry]:
    """Merge new history entries with existing ones.

    Deduplicates by (server_url, issue_key) tuple. New entries replace
    existing entries for the same issue (handles updates). Existing entries
    not in the new set are preserved (handles issues not in incremental query).

    Args:
        existing: Existing history entries
        new: New history entries to merge

    Returns:
        Merged list with duplicates resolved (new entries win)
    """
    # Build lookup by (server_url, issue_key)
    entries_by_key: dict[tuple[str, str], JiraDurationHistoryEntry] = {}

    # Add existing entries first
    for entry in existing:
        key = (entry.server_url, str(entry.issue_key))
        entries_by_key[key] = entry

    # New entries override existing
    for entry in new:
        key = (entry.server_url, str(entry.issue_key))
        entries_by_key[key] = entry

    return list(entries_by_key.values())


def _update_parent_relationships(
    issues: list[JiraIssueResponse],
    hierarchy: dict[str, HierarchyEntry],
    task_id_by_key: dict[str, TaskId],
    new_node_map: dict[TaskId | BranchId, PersistentObjectId],
    new_persistent_tasks: dict[PersistentObjectId, PersistentTask],
    new_version_id: DAGVersionId,
) -> None:
    """Update parent relationships for tasks based on Jira hierarchy.

    This is extracted as a separate function to enable direct testing of
    edge cases where data structures may be inconsistent.

    Args:
        issues: List of Jira issues to process
        hierarchy: Map of issue_key -> HierarchyEntry with parent info
        task_id_by_key: Map of issue_key -> TaskId
        new_node_map: Map of NodeId -> PersistentObjectId (may contain branches)
        new_persistent_tasks: Map of PersistentObjectId -> PersistentTask
        new_version_id: The new DAG version ID for updated tasks
    """
    for issue in issues:
        issue_key = issue.key
        entry = hierarchy.get(issue_key)
        if entry is None:
            continue

        maybe_task_id = task_id_by_key.get(issue_key)
        if maybe_task_id is None:
            continue
        tid = maybe_task_id

        parent_task_id: TaskId | None = None
        if entry.parent_key and entry.parent_key in task_id_by_key:
            parent_task_id = task_id_by_key[entry.parent_key]

        # Get the persistent task and update parent_id
        maybe_persistent_id = new_node_map.get(tid)
        if maybe_persistent_id is None:
            continue
        pid = maybe_persistent_id

        maybe_ptask = new_persistent_tasks.get(pid)
        if maybe_ptask is None:
            continue
        ptask = maybe_ptask

        task = ptask.versions.get(new_version_id)
        if task is None:
            continue

        if task.parent_id != parent_task_id:
            updated_task = task.model_copy(update={"parent_id": parent_task_id})
            new_versions = dict(ptask.versions)
            new_versions[new_version_id] = updated_task
            new_persistent_tasks[pid] = ptask.model_copy(
                update={"versions": new_versions}
            )


def _sync_update_project(
    project: Project,
    issues: list[JiraIssueResponse],
    existing_tasks: dict[str, tuple[TaskId, Task]],
    server_url: str,
    server_timezone: str,
) -> tuple[Project, int, int, list[str], list[ImportWarningFluxx]]:
    """Update project with synced Jira data.

    Args:
        project: The project to update
        issues: Fresh Jira issues
        existing_tasks: Map of issue_key -> (task_id, task) for existing tasks
        server_url: Jira server URL
        server_timezone: Server timezone for datetime parsing

    Returns:
        Tuple of (updated_project, updated_count, created_count,
                  deleted_keys, warnings)
    """
    warnings: list[ImportWarningFluxx] = []
    updated_count = 0
    created_count = 0

    # Build a set of issue keys we received from Jira
    fetched_keys = {issue.key for issue in issues}

    # Find keys that were in the project but no longer in Jira
    deleted_keys = [key for key in existing_tasks if key not in fetched_keys]

    # Extract workers from all issues (needed for completion extraction)
    workers_by_jira_id: dict[str, WorkerId] = {}
    for worker in project.workers:
        if worker.jira_user_id:
            workers_by_jira_id[worker.jira_user_id] = worker.id

    # Also extract any new workers from the issues
    new_workers_from_issues = extract_workers_with_no_hours(issues)
    for jira_id, worker in new_workers_from_issues.items():
        if jira_id not in workers_by_jira_id:
            workers_by_jira_id[jira_id] = worker.id

    # Build hierarchy from fetched issues
    hierarchy, hierarchy_warnings = build_hierarchy(issues)
    for hw in hierarchy_warnings:
        warnings.append(ImportWarningFluxx(issue_key=hw.issue_key, message=hw.message))

    # Create new DAG version for all changes
    new_version_id = generate_dag_version_id()
    event_id = generate_event_id()

    # Copy persistent tasks and update/create as needed
    new_persistent_tasks = dict(project.persistent_tasks)
    new_node_map = dict(project.dag.node_map)

    # Track task_id by issue_key for parent resolution
    task_id_by_key: dict[str, TaskId] = {}

    # Process each fetched issue
    for issue in issues:
        issue_key = issue.key
        existing = existing_tasks.get(issue_key)

        if existing is not None:
            # Update existing task
            task_id, old_task = existing
            task_id_by_key[issue_key] = task_id

            # Extract new completion and other data
            completion_result = extract_completion(
                issue, workers_by_jira_id, server_timezone
            )

            # Get duration distribution
            original_estimate = None
            remaining_estimate = None
            if issue.fields.timetracking:
                original_estimate = issue.fields.timetracking.original_estimate_seconds
                remaining_estimate = (
                    issue.fields.timetracking.remaining_estimate_seconds
                )

            new_dist = JiraDurationDistribution(
                original_estimate_seconds=original_estimate,
                story_points=issue.fields.story_points,
                remaining_estimate_seconds=remaining_estimate,
            )

            # Update the task
            updated_task = old_task.model_copy(
                update={
                    "title": issue.fields.summary,
                    "description": issue.fields.description or "",
                    "completion": completion_result.completion,
                    "duration_distribution": new_dist,
                    "jira_issue_type": issue.fields.issuetype.name,
                    # parent_id updated in second pass
                }
            )

            # Update persistent task with new version
            persistent_id = project.dag.node_map[task_id]
            ptask = new_persistent_tasks[persistent_id]
            new_versions = dict(ptask.versions)
            new_versions[new_version_id] = updated_task
            new_persistent_tasks[persistent_id] = ptask.model_copy(
                update={"versions": new_versions}
            )

            updated_count += 1
        else:
            # Create new task
            new_task = extract_task(
                issue=issue,
                workers=workers_by_jira_id,
                server_url=server_url,
                parent_id=None,  # Set in second pass
                server_timezone=server_timezone,
            )
            task_id_by_key[issue_key] = new_task.id

            # Create persistent task
            persistent_id = PersistentObjectId(str(new_task.id))
            new_persistent_tasks[persistent_id] = PersistentTask(
                id=persistent_id,
                versions={new_version_id: new_task},
            )
            new_node_map[new_task.id] = persistent_id

            created_count += 1

    # Second pass: update parent relationships
    _update_parent_relationships(
        issues=issues,
        hierarchy=hierarchy,
        task_id_by_key=task_id_by_key,
        new_node_map=new_node_map,
        new_persistent_tasks=new_persistent_tasks,
        new_version_id=new_version_id,
    )

    # Copy versions for tasks not touched in this sync
    for persistent_id, ptask in project.persistent_tasks.items():
        if persistent_id in new_persistent_tasks:
            # Check if we've already added new_version_id
            existing_ptask = new_persistent_tasks[persistent_id]
            if new_version_id not in existing_ptask.versions:
                # Copy the current version to new version
                current_version = ptask.versions.get(project.dag.current_version_id)
                if current_version is not None:
                    new_versions = dict(existing_ptask.versions)
                    new_versions[new_version_id] = current_version
                    new_persistent_tasks[persistent_id] = existing_ptask.model_copy(
                        update={"versions": new_versions}
                    )

    # Copy persistent branches to new version
    new_persistent_branches: dict[PersistentObjectId, PersistentBranch] = {}
    for branch_persistent_id, pbranch in project.persistent_branches.items():
        branch_version = pbranch.versions.get(project.dag.current_version_id)
        if branch_version is not None:
            new_persistent_branches[branch_persistent_id] = pbranch.model_copy(
                update={
                    "versions": {
                        **pbranch.versions,
                        new_version_id: branch_version,
                    }
                }
            )

    # Handle deleted tasks - remove from node_map
    for deleted_key in deleted_keys:
        task_id, _task = existing_tasks[deleted_key]
        if task_id in new_node_map:
            del new_node_map[task_id]
            warnings.append(
                ImportWarningFluxx(
                    issue_key=deleted_key,
                    message="Task removed from Jira - deleted from project",
                )
            )

    # Add new workers to project
    existing_worker_jira_ids = {
        w.jira_user_id for w in project.workers if w.jira_user_id
    }
    new_workers = list(project.workers)
    for jira_id, worker in new_workers_from_issues.items():
        if jira_id not in existing_worker_jira_ids:
            new_workers.append(worker)

    # Create new DAG
    new_dag = DAG(
        id=project.dag.id,
        current_version_id=new_version_id,
        node_map=new_node_map,
    )

    # Create history event
    event = DAGEvent(
        id=event_id,
        timestamp=datetime.now().astimezone(),
        parent_event_id=project.current_event_id,
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[],  # Could track updated task IDs here
        resulting_dag_version=new_version_id,
    )

    # Build updated project
    new_history = list(project.history_events) + [event]
    updated_project = project.model_copy(
        update={
            "dag": new_dag,
            "persistent_tasks": new_persistent_tasks,
            "persistent_branches": new_persistent_branches,
            "history_events": new_history,
            "current_event_id": event_id,
            "workers": new_workers,
            "metadata": project.metadata.model_copy(
                update={"last_modified": datetime.now().astimezone()}
            ),
        }
    )

    return updated_project, updated_count, created_count, deleted_keys, warnings


def sync_from_jira(
    project: Project,
    client: JiraClient,
    config: JiraConfig,
    progress_callback: Callable[[ImportProgress], None] | None = None,
) -> SyncResult:
    """Sync all Jira-linked tasks in the project with Jira.

    This function:
    1. Collects all tasks with jira_reference in the project
    2. Fetches fresh data from Jira (including children)
    3. Updates existing tasks with new data
    4. Creates new tasks for new issues
    5. Deletes tasks that were removed from Jira

    Args:
        project: The project to sync
        client: Configured Jira client for the server
        config: Jira configuration
        progress_callback: Optional callback for progress updates

    Returns:
        SyncResult with the updated project and sync statistics
    """
    update_progress = generate_progress_updater(progress_callback)
    warnings: list[ImportWarningFluxx] = []
    total_updated = 0
    total_created = 0
    all_deleted_keys: list[str] = []

    # Collect all Jira-referenced tasks grouped by server
    tasks_by_server = collect_jira_referenced_tasks(project)

    # Only sync tasks for the provided server
    server_url = config.server_url.rstrip("/")
    server_tasks = tasks_by_server.get(server_url, {})

    if not server_tasks:
        # No tasks to sync for this server
        return SyncResult(
            project=project,
            updated_count=0,
            created_count=0,
            deleted_keys=[],
            warnings=[],
        )

    update_progress("collecting_tasks", 0, len(server_tasks))

    # Build JQL to fetch all the issues we need to sync
    issue_keys = list(server_tasks.keys())
    jql = build_sync_jql(issue_keys)

    # Fetch issues including their children
    update_progress("fetching_issues", 0, len(issue_keys))
    issues = fetch_all_issues_with_children(client, jql, update_progress)

    update_progress("updating_tasks", len(issues) // 2, len(issues))

    # Update the project
    (
        updated_project,
        updated_count,
        created_count,
        deleted_keys,
        sync_warnings,
    ) = _sync_update_project(
        project=project,
        issues=issues,
        existing_tasks=server_tasks,
        server_url=server_url,
        server_timezone=config.server_timezone,
    )

    total_updated += updated_count
    total_created += created_count
    all_deleted_keys.extend(deleted_keys)
    warnings.extend(sync_warnings)

    update_progress("sync_complete", len(issues), len(issues))

    return SyncResult(
        project=updated_project,
        updated_count=total_updated,
        created_count=total_created,
        deleted_keys=all_deleted_keys,
        warnings=warnings,
    )
