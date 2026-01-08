"""Jira import orchestration for Project Fluxx.

This module provides the high-level orchestration for importing Jira projects
into Fluxx, coordinating the client, extraction, and distribution fitting
components.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fluxx.data.id_generation import (
    generate_dag_id,
    generate_dag_version_id,
    generate_event_id,
    generate_task_id,
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
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.jira.api_types import JiraIssueResponse, JiraWorklogEntry
from fluxx.jira.client import JiraClient

# Note: Empirical bin-based sampling happens at simulation time, not during import.
# The import process stores JiraDurationDistribution with raw parameters.
from fluxx.jira.extraction import (
    BLOCKS_LINK_TYPES,
    DEPENDS_ON_LINK_TYPES,
    HierarchyEntry,
    _is_child_of_link,
    _is_parent_of_link,
    build_hierarchy,
    calculate_hours_per_workday,
    extract_completion,
    extract_dependencies,
    extract_task,
    extract_workers_with_no_hours,
    parse_jira_datetime,
)
from fluxx.jira.models import (
    JiraConfig,
    JiraDurationHistoryEntry,
    JiraIssueKey,
    JiraReference,
    JiraSyncMetadata,
)

logger = logging.getLogger(__name__)


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
    history_entries_added: int = 0


@dataclass
class InaccessibleIssue:
    """Represents an issue that could not be fetched from Jira.

    Used to track dependency targets that are referenced but inaccessible
    (possibly due to permissions or the issue being deleted).
    """

    issue_key: str
    referenced_from: str  # The issue key that referenced this one


@dataclass
class FetchResult:
    """Result of fetching issues from Jira.

    Includes both successfully fetched issues and keys that couldn't be accessed.
    """

    issues: list[JiraIssueResponse]
    inaccessible: list[InaccessibleIssue] = field(default_factory=list)


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


def get_dependencies_from_links(
    issues: list[JiraIssueResponse],
    already_fetched: set[str],
) -> set[str]:
    """Extract dependency target issue keys from issue links.

    This finds issues that the given issues depend on (blocking dependencies).

    Args:
        issues: List of Jira issues to examine
        already_fetched: Set of issue keys already fetched (to exclude)

    Returns:
        Set of issue keys that are dependency targets but not yet fetched
    """
    dependency_keys: set[str] = set()

    for issue in issues:
        if not issue.fields.issuelinks:
            continue

        for link in issue.fields.issuelinks:
            target_key: str | None = None

            # "depends on" type outward link: this issue depends on the outward issue
            if link.link_type.name in DEPENDS_ON_LINK_TYPES and link.outward_issue:
                target_key = link.outward_issue.key

            # "blocks" type inward link: inward issue blocks this issue
            # (so this issue depends on the inward issue)
            if link.link_type.name in BLOCKS_LINK_TYPES and link.inward_issue:
                target_key = link.inward_issue.key

            if target_key is not None and target_key not in already_fetched:
                dependency_keys.add(target_key)

    return dependency_keys


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
) -> FetchResult:
    """Fetch issues matching JQL, all their descendants, and all dependencies.

    Uses a queue-based iterative approach to fetch all related issues:
    1. Fetch initial issues from JQL
    2. For each batch of issues, fetch their children via Epic Link/parent
    3. Check links for "parent of"/"child of" references
    4. Check links for "depends on"/"blocks" references (dependency targets)
    5. Repeat until no new issues found

    Inaccessible dependency targets (due to permissions or deletion) are tracked
    and returned separately for dummy task creation.

    Args:
        client: Jira client
        initial_jql: Initial JQL query
        progress_callback: Optional callback(phase, processed, total)

    Returns:
        FetchResult containing fetched issues and inaccessible issue keys
    """
    logger.debug("Fetching issues with children for JQL: %s", initial_jql)
    if progress_callback:
        progress_callback("fetching_issues", 0, 0)

    # Track all fetched issues by key (for deduplication)
    issues_by_key: dict[str, JiraIssueResponse] = {}

    # Track which issues we've already fetched children for
    children_fetched_for: set[str] = set()

    # Track inaccessible issues (key -> referencing issue key)
    inaccessible_issues: dict[str, str] = {}

    # Track issues we've already tried to fetch (to avoid repeated failures)
    fetch_attempted: set[str] = set()

    # Fetch initial issues
    for issue_dict in client.search(initial_jql, REQUIRED_FIELDS, expand=["changelog"]):
        issue = JiraIssueResponse.model_validate(issue_dict)
        issues_by_key[issue.key] = issue
        fetch_attempted.add(issue.key)

    if progress_callback:
        progress_callback("fetching_children", 0, len(issues_by_key))

    # Iteratively fetch children and dependencies until no new issues found
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
            fetch_attempted.add(issue.key)
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
            if child_key not in issues_by_key and child_key not in fetch_attempted:
                fetch_attempted.add(child_key)
                try:
                    issue_dict = client.get_issue(
                        child_key, REQUIRED_FIELDS, expand=["changelog"]
                    )
                    issue = JiraIssueResponse.model_validate(issue_dict)
                    issues_by_key[issue.key] = issue
                except Exception:
                    # Issue might not exist or not accessible - skip it
                    # (children don't need dummy tasks, only dependencies do)
                    pass

        # Check for dependency targets referenced in links but not yet fetched
        dependency_targets = get_dependencies_from_links(
            list(issues_by_key.values()), set(issues_by_key.keys())
        )

        # Fetch any dependency targets individually
        deps_added = 0
        for dep_key in dependency_targets:
            if dep_key not in issues_by_key and dep_key not in fetch_attempted:
                fetch_attempted.add(dep_key)
                # Find which issue references this dependency
                referencing_issue = _find_referencing_issue(
                    dep_key, list(issues_by_key.values())
                )
                try:
                    issue_dict = client.get_issue(
                        dep_key, REQUIRED_FIELDS, expand=["changelog"]
                    )
                    issue = JiraIssueResponse.model_validate(issue_dict)
                    issues_by_key[issue.key] = issue
                    deps_added += 1
                    logger.debug(
                        "Fetched dependency target %s (referenced from %s)",
                        dep_key,
                        referencing_issue,
                    )
                except Exception as e:
                    # Dependency target is inaccessible - track it for dummy task
                    inaccessible_issues[dep_key] = referencing_issue
                    logger.debug(
                        "Could not fetch dependency target %s (referenced from %s): %s",
                        dep_key,
                        referencing_issue,
                        e,
                    )

        # If no new issues were added, we're done
        if new_issues_count == 0 and len(link_children) == 0 and deps_added == 0:
            break

    logger.debug(
        "Fetched %d total issues, %d inaccessible dependency targets",
        len(issues_by_key),
        len(inaccessible_issues),
    )

    # Build inaccessible issues list
    inaccessible_list = [
        InaccessibleIssue(issue_key=key, referenced_from=ref)
        for key, ref in inaccessible_issues.items()
    ]

    return FetchResult(
        issues=list(issues_by_key.values()),
        inaccessible=inaccessible_list,
    )


def _find_referencing_issue(dep_key: str, issues: list[JiraIssueResponse]) -> str:
    """Find which issue references a given dependency target.

    Args:
        dep_key: The dependency target key to find
        issues: List of issues to search

    Returns:
        The key of the issue that references dep_key, or "unknown"
    """
    for issue in issues:
        if not issue.fields.issuelinks:
            continue
        for link in issue.fields.issuelinks:
            # Check outward "depends on" links
            if (
                link.link_type.name in DEPENDS_ON_LINK_TYPES
                and link.outward_issue
                and link.outward_issue.key == dep_key
            ):
                return issue.key
            # Check inward "blocks" links
            if (
                link.link_type.name in BLOCKS_LINK_TYPES
                and link.inward_issue
                and link.inward_issue.key == dep_key
            ):
                return issue.key
    return "unknown"


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

        # Get original estimate and remaining estimate
        original_estimate = None
        remaining_estimate = None
        if issue.fields.timetracking:
            original_estimate = issue.fields.timetracking.original_estimate_seconds
            remaining_estimate = issue.fields.timetracking.remaining_estimate_seconds

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

        # Parse datetime fields (convert to UTC-aware)
        created_dt = None
        if issue.fields.created:
            naive_dt = parse_jira_datetime(issue.fields.created, server_timezone)
            created_dt = naive_dt.replace(tzinfo=UTC)
        resolved_dt = None
        if issue.fields.resolutiondate:
            naive_dt = parse_jira_datetime(issue.fields.resolutiondate, server_timezone)
            resolved_dt = naive_dt.replace(tzinfo=UTC)

        entries.append(
            JiraDurationHistoryEntry(
                server_url=server_url,
                issue_key=JiraIssueKey.from_string(issue.key),
                original_estimate_seconds=original_estimate,
                worker_jira_id=worker_jira_id,
                issue_type=issue.fields.issuetype.name,
                total_logged_time_seconds=total_seconds,
                remaining_estimate_seconds=remaining_estimate,
                story_points=issue.fields.story_points,
                created_datetime=created_dt,
                resolved_datetime=resolved_dt,
            )
        )

    return entries


def create_dummy_task(
    issue_key: str,
    referenced_from: str,
    server_url: str,
) -> Task:
    """Create a dummy task for an inaccessible Jira issue.

    This is used when a dependency target cannot be fetched (due to permissions
    or deletion) but we need a task to represent it in the project.

    Args:
        issue_key: The Jira issue key (e.g., "CORE-123")
        referenced_from: The issue key that references this dependency
        server_url: Jira server URL for the jira_reference

    Returns:
        A Task with minimal information representing the inaccessible issue
    """
    jira_key = JiraIssueKey.from_string(issue_key)

    description = (
        f"{issue_key} could not be imported but was referenced from "
        f"{referenced_from}, so this dummy task was created to act as a stand-in."
    )

    return Task(
        id=generate_task_id(),
        title=f"Dummy task for {issue_key}",
        description=description,
        # Use a tiny duration since Triangular requires mode > min and max > mode
        duration_distribution=Triangular(min=0.0, mode=0.001, max=0.002),
        jira_reference=JiraReference(
            server_url=server_url,
            issue_key=jira_key,
        ),
        jira_issue_type="Dummy",
    )


def _build_duration_distribution(
    issue: JiraIssueResponse,
) -> JiraDurationDistribution:
    """Build duration distribution for an issue.

    All Jira-imported tasks use JiraDurationDistribution which stores the raw
    estimate parameters. Actual sampling from historical data happens at
    simulation time using empirical bins.

    Args:
        issue: The Jira issue

    Returns:
        JiraDurationDistribution containing the issue's estimate data
    """
    original_estimate_seconds: int | None = None
    remaining_estimate_seconds: int | None = None
    story_points = issue.fields.story_points

    if issue.fields.timetracking:
        original_estimate_seconds = issue.fields.timetracking.original_estimate_seconds
        remaining_estimate_seconds = (
            issue.fields.timetracking.remaining_estimate_seconds
        )

    return JiraDurationDistribution(
        original_estimate_seconds=original_estimate_seconds,
        story_points=story_points,
        remaining_estimate_seconds=remaining_estimate_seconds,
    )


def _build_project(
    issues: list[JiraIssueResponse],
    workers: dict[str, Worker],
    config: JiraConfig,
    project_name: str,
    inaccessible: list[InaccessibleIssue] | None = None,
) -> tuple[Project, list[ImportWarningFluxx]]:
    """Build a Project from extracted Jira data.

    Args:
        issues: All Jira issues to import
        workers: Extracted workers keyed by Jira account ID
        config: Jira configuration
        project_name: Name for the project
        inaccessible: List of inaccessible issues to create dummy tasks for

    Returns:
        Tuple of (Project, list of warnings)
    """
    warnings: list[ImportWarningFluxx] = []

    # Create dummy tasks for inaccessible dependency targets
    dummy_tasks: dict[str, Task] = {}
    if inaccessible:
        dummy_keys = [i.issue_key for i in inaccessible]
        for inacc in inaccessible:
            dummy = create_dummy_task(
                issue_key=inacc.issue_key,
                referenced_from=inacc.referenced_from,
                server_url=config.server_url,
            )
            dummy_tasks[inacc.issue_key] = dummy

        # Add warning about dummy tasks
        if dummy_keys:
            warnings.append(
                ImportWarningFluxx(
                    issue_key="",
                    message=(
                        f"Dummy tasks ({', '.join(sorted(dummy_keys))}) were created "
                        "because the originals could not be accessed."
                    ),
                )
            )

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
    # Start with dummy tasks for inaccessible issues
    task_by_key: dict[str, Task] = dict(dummy_tasks)
    for issue in issues:
        task = extract_task(
            issue=issue,
            workers=workers_by_jira_id,
            server_url=config.server_url,
            parent_id=None,  # Set in second pass
            server_timezone=config.server_timezone,
        )

        # Set duration distribution (JiraDurationDistribution with raw parameters)
        dist = _build_duration_distribution(issue)
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
        jira_config=config,
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

    This function:
    1. Fetches issues matching the JQL query (and their children)
    2. Extracts workers from worklogs
    3. Fetches project-wide history for ALL completed issues in referenced projects
    4. Fits duration distributions using the project-wide history
    5. Creates the Fluxx project with jira_config containing history entries

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
    logger.info("Starting Jira import: project_name=%s, jql=%s", project_name, jql)
    update_progress = generate_progress_updater(progress_callback)

    # Fetch all issues including children and dependencies recursively
    fetch_result = fetch_all_issues_with_children(client, jql, update_progress)
    issues = fetch_result.issues
    inaccessible = fetch_result.inaccessible

    update_progress("extracting_workers", 0, len(issues))

    workers = extract_workers(issues)

    update_progress("building_history", len(issues) // 2, len(issues))

    # Extract project keys from imported issues to determine which projects
    # we need to fetch history for
    project_keys: set[str] = set()
    for issue in issues:
        key = JiraIssueKey.from_string(issue.key)
        project_keys.add(key.project_key)

    # Fetch project-wide history for ALL completed issues in referenced projects
    # This is the full history used for distribution fitting (per spec section 11.5.1)
    history_entries: list[JiraDurationHistoryEntry] = []
    if project_keys:
        history_entries = fetch_history_entries(
            client=client,
            project_keys=project_keys,
            last_sync=None,  # First import - fetch all history
            server_url=config.server_url,
            server_timezone=config.server_timezone,
        )

    # Note: Distribution fitting happens at simulation time using empirical bins.
    # The import process just stores JiraDurationDistribution with raw parameters.

    update_progress("building_project", len(issues), len(issues))

    # Create updated config with history entries
    now = datetime.now().astimezone()
    updated_config = JiraConfig(
        server_url=config.server_url,
        server_timezone=config.server_timezone,
        sync_metadata=JiraSyncMetadata(
            server_url=config.server_url,
            last_history_sync=now,
            history_entries=history_entries,
        ),
    )

    # Build the project (including dummy tasks for inaccessible dependencies)
    project, warnings = _build_project(
        issues=issues,
        workers=workers,
        config=updated_config,
        project_name=project_name,
        inaccessible=inaccessible,
    )

    logger.info(
        "Jira import complete: %d issues, %d inaccessible, %d history entries, "
        "%d warnings",
        len(issues),
        len(inaccessible),
        len(history_entries),
        len(warnings),
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

    logger.debug(
        "Fetching history for %d projects, last_sync=%s",
        len(project_keys),
        last_sync.isoformat() if last_sync else "None",
    )
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
    entries = _create_history_entries(issues, {}, server_url, server_timezone)
    logger.debug("Created %d history entries from %d issues", len(entries), len(issues))
    return entries


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
    6. Fetches and merges history entries for distribution fitting

    Args:
        project: The project to sync
        client: Configured Jira client for the server
        config: Jira configuration
        progress_callback: Optional callback for progress updates

    Returns:
        SyncResult with the updated project and sync statistics
    """
    logger.info("Starting Jira sync for server: %s", config.server_url)
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

    # Fetch issues including their children and dependencies
    update_progress("fetching_issues", 0, len(issue_keys))
    fetch_result = fetch_all_issues_with_children(client, jql, update_progress)
    issues = fetch_result.issues
    inaccessible = fetch_result.inaccessible

    # Check which originally requested tasks could not be fetched
    fetched_keys = {issue.key for issue in issues}
    unfetched_keys = [key for key in issue_keys if key not in fetched_keys]
    if unfetched_keys:
        warnings.append(
            ImportWarningFluxx(
                issue_key="",
                message=(
                    f"Unable to update ({', '.join(sorted(unfetched_keys))}) "
                    "due to inability to access those tasks."
                ),
            )
        )

    # Add warning about inaccessible dependency targets
    if inaccessible:
        inacc_keys = sorted([i.issue_key for i in inaccessible])
        warnings.append(
            ImportWarningFluxx(
                issue_key="",
                message=(
                    f"Dependency targets ({', '.join(inacc_keys)}) could not be "
                    "accessed and were skipped during sync."
                ),
            )
        )

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

    # Phase 4: Sync history entries for distribution fitting
    update_progress("syncing_history", len(issues), len(issues))

    # Collect all project keys from synced tasks
    project_keys = collect_jira_project_keys(updated_project)

    # Get existing history and last sync time from config
    existing_history: list[JiraDurationHistoryEntry] = []
    last_history_sync: datetime | None = None
    if config.sync_metadata:
        existing_history = config.sync_metadata.history_entries
        last_history_sync = config.sync_metadata.last_history_sync

    # Fetch new/updated history entries since last sync
    history_entries_added = 0
    if project_keys:
        new_history = fetch_history_entries(
            client=client,
            project_keys=project_keys,
            last_sync=last_history_sync,
            server_url=config.server_url,
            server_timezone=config.server_timezone,
        )
        history_entries_added = len(new_history)

        # Merge with existing history entries
        merged_history = merge_history_entries(existing_history, new_history)

        # Create updated config with new history
        now = datetime.now().astimezone()
        updated_config = JiraConfig(
            server_url=config.server_url,
            server_timezone=config.server_timezone,
            sync_metadata=JiraSyncMetadata(
                server_url=config.server_url,
                last_history_sync=now,
                history_entries=merged_history,
            ),
        )

        # Update the project's jira_config
        updated_project = updated_project.model_copy(
            update={"jira_config": updated_config}
        )

    update_progress("sync_complete", len(issues), len(issues))

    logger.info(
        "Jira sync complete: updated=%d, created=%d, deleted=%d, history_added=%d",
        total_updated,
        total_created,
        len(all_deleted_keys),
        history_entries_added,
    )
    return SyncResult(
        project=updated_project,
        updated_count=total_updated,
        created_count=total_created,
        deleted_keys=all_deleted_keys,
        warnings=warnings,
        history_entries_added=history_entries_added,
    )
