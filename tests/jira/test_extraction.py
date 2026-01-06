"""Tests for Jira data extraction to Fluxx models."""

import pytest

from fluxx.data.models import (
    DoneCompletion,
    NotStartedCompletion,
    StartedCompletion,
    WorkerId,
)
from fluxx.jira.api_types import (
    JiraIssueFields,
    JiraIssueLink,
    JiraIssueLinkType,
    JiraIssueResponse,
    JiraIssueType,
    JiraLinkedIssue,
    JiraParentRef,
    JiraStatus,
    JiraTimeTracking,
    JiraUser,
    JiraWorklog,
    JiraWorklogEntry,
)
from fluxx.jira.extraction import (
    build_hierarchy,
    calculate_hours_per_workday,
    extract_completion,
    extract_dependencies,
    extract_task,
    extract_workers_with_no_hours,
    get_earliest_worklog_time,
    get_latest_worklog_time,
    parse_jira_datetime,
)


def _make_issue(
    key: str = "FHIR-100",
    summary: str = "Test issue",
    status: str = "Open",
    issue_type: str = "Story",
    assignee_id: str | None = None,
    assignee_name: str | None = None,
    worklogs: list[JiraWorklogEntry] | None = None,
    resolution_date: str | None = None,
    parent_key: str | None = None,
    links: list[JiraIssueLink] | None = None,
    original_estimate_seconds: int | None = None,
    story_points: float | None = None,
    description: str | None = None,
) -> JiraIssueResponse:
    """Helper to create JiraIssueResponse for testing."""
    assignee = None
    if assignee_id:
        assignee = JiraUser(
            account_id=assignee_id,
            display_name=assignee_name or assignee_id,
        )

    worklog = None
    if worklogs is not None:
        worklog = JiraWorklog(
            start_at=0,
            max_results=len(worklogs),
            total=len(worklogs),
            worklogs=worklogs,
        )

    parent = None
    if parent_key:
        parent = JiraParentRef(id="parent-id", key=parent_key)

    timetracking = None
    if original_estimate_seconds is not None:
        timetracking = JiraTimeTracking(
            original_estimate_seconds=original_estimate_seconds,
        )

    fields = JiraIssueFields(
        summary=summary,
        description=description,
        issuetype=JiraIssueType(id="1", name=issue_type),
        status=JiraStatus(id="1", name=status),
        assignee=assignee,
        worklog=worklog,
        resolutiondate=resolution_date,
        parent=parent,
        issuelinks=links,
        timetracking=timetracking,
        story_points=story_points,
    )

    return JiraIssueResponse(
        id="100",
        key=key,
        fields=fields,
    )


def _make_worklog(
    author_id: str,
    started: str,
    time_spent_seconds: int,
    author_name: str | None = None,
) -> JiraWorklogEntry:
    """Helper to create worklog entries."""
    return JiraWorklogEntry(
        id="wl-1",
        author=JiraUser(
            account_id=author_id,
            display_name=author_name or author_id,
        ),
        started=started,
        time_spent="1h",
        time_spent_seconds=time_spent_seconds,
    )


def _make_link(
    link_type_name: str,
    outward_key: str | None = None,
    inward_key: str | None = None,
) -> JiraIssueLink:
    """Helper to create issue links."""
    return JiraIssueLink(
        id="link-1",
        link_type=JiraIssueLinkType(name=link_type_name),
        outward_issue=JiraLinkedIssue(id="out-id", key=outward_key)
        if outward_key
        else None,
        inward_issue=JiraLinkedIssue(id="in-id", key=inward_key)
        if inward_key
        else None,
    )


class TestExtractCompletion:
    """Tests for extract_completion function."""

    def test_extract_completion_not_started_no_worklogs(self) -> None:
        """Issue with no worklogs and no resolution is not started."""
        issue = _make_issue(worklogs=[])
        workers: dict[str, WorkerId] = {}

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, NotStartedCompletion)
        assert result.allowed_workers is None

    def test_extract_completion_not_started_with_assignee_sets_allowed_workers(
        self,
    ) -> None:
        """Not-started issue with assignee should set allowed_workers."""
        worker_id = WorkerId("worker-1")
        workers = {"user-123": worker_id}
        issue = _make_issue(assignee_id="user-123", worklogs=[])

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, NotStartedCompletion)
        assert result.allowed_workers == [worker_id]

    def test_extract_completion_started_has_worklogs_no_resolution(self) -> None:
        """Issue with worklogs but no resolution is in progress."""
        worker_id = WorkerId("worker-1")
        workers = {"user-123": worker_id}
        worklogs = [
            _make_worklog("user-123", "2024-01-15T10:00:00.000+0000", 3600),
        ]
        issue = _make_issue(worklogs=worklogs)

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, StartedCompletion)
        assert result.completion.assignee == worker_id
        assert result.completion.hours_logged == 1.0  # 3600 seconds = 1 hour

    def test_extract_completion_done_with_work_logged(self) -> None:
        """Done issue with worklogs uses last worklog date as end_time."""
        worker_id = WorkerId("worker-1")
        workers = {"user-123": worker_id}
        worklogs = [
            _make_worklog("user-123", "2024-01-15T10:00:00.000+0000", 3600),
            _make_worklog("user-123", "2024-01-16T14:00:00.000+0000", 7200),
        ]
        issue = _make_issue(
            worklogs=worklogs,
            resolution_date="2024-01-20T12:00:00.000+0000",
        )

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, DoneCompletion)
        assert result.completion.assignee == worker_id
        assert result.completion.hours_logged == 3.0  # 3600 + 7200 = 10800 sec = 3h
        # End time should be last worklog date, not resolution date
        assert result.completion.end_time.day == 16

    def test_extract_completion_done_without_work_uses_resolution_date(self) -> None:
        """Done issue without worklogs uses resolution_date and epsilon hours."""
        workers: dict[str, WorkerId] = {}
        issue = _make_issue(
            worklogs=[],
            resolution_date="2024-01-20T12:00:00.000+0000",
        )

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, DoneCompletion)
        assert result.completion.hours_logged == 1e-6  # Epsilon for zero-work tasks
        assert result.completion.end_time.day == 20

    def test_extract_completion_uses_most_worklogs_when_no_assignee(self) -> None:
        """When no assignee, use worker with most logged time."""
        worker1_id = WorkerId("worker-1")
        worker2_id = WorkerId("worker-2")
        workers = {"user-1": worker1_id, "user-2": worker2_id}
        worklogs = [
            _make_worklog("user-1", "2024-01-15T10:00:00.000+0000", 3600),  # 1 hour
            _make_worklog("user-2", "2024-01-15T11:00:00.000+0000", 7200),  # 2 hours
            _make_worklog("user-2", "2024-01-16T10:00:00.000+0000", 3600),  # 1 hour
        ]
        issue = _make_issue(worklogs=worklogs)

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, StartedCompletion)
        # user-2 has 3 hours total, user-1 has 1 hour
        assert result.completion.assignee == worker2_id

    def test_extract_completion_assignee_takes_priority_over_worklogs(self) -> None:
        """Assignee takes priority over worker with most worklogs."""
        worker1_id = WorkerId("worker-1")
        worker2_id = WorkerId("worker-2")
        workers = {"user-1": worker1_id, "user-2": worker2_id}
        worklogs = [
            _make_worklog("user-2", "2024-01-15T11:00:00.000+0000", 36000),  # 10 hours
        ]
        issue = _make_issue(assignee_id="user-1", worklogs=worklogs)

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, StartedCompletion)
        # Even though user-2 logged all the work, assignee (user-1) is used
        assert result.completion.assignee == worker1_id


class TestExtractDependencies:
    """Tests for extract_dependencies function."""

    def test_extract_dependencies_depends_on_link(self) -> None:
        """'Depends' link creates a dependency."""
        links = [_make_link("Depends", outward_key="FHIR-200")]
        issue = _make_issue(key="FHIR-100", links=links)
        task_map = {"FHIR-200": "task-200-id"}

        deps = extract_dependencies(issue, task_map)

        assert len(deps) == 1
        assert deps[0].target_key == "FHIR-200"

    def test_extract_dependencies_blocks_link(self) -> None:
        """'Blocks' inward link creates a dependency."""
        links = [_make_link("Blocks", inward_key="FHIR-200")]
        issue = _make_issue(key="FHIR-100", links=links)
        task_map = {"FHIR-200": "task-200-id"}

        deps = extract_dependencies(issue, task_map)

        assert len(deps) == 1
        assert deps[0].target_key == "FHIR-200"

    def test_extract_dependencies_skip_when_both_started(self) -> None:
        """Skip dependency when both issues have been started."""
        links = [_make_link("Depends", outward_key="FHIR-200")]
        issue = _make_issue(key="FHIR-100", links=links)
        task_map = {"FHIR-200": "task-200-id"}
        started_issues = {"FHIR-100", "FHIR-200"}

        deps = extract_dependencies(issue, task_map, started_issues=started_issues)

        assert len(deps) == 0  # Skipped because both started

    def test_extract_dependencies_keep_when_only_one_started(self) -> None:
        """Keep dependency when only source issue started."""
        links = [_make_link("Depends", outward_key="FHIR-200")]
        issue = _make_issue(key="FHIR-100", links=links)
        task_map = {"FHIR-200": "task-200-id"}
        started_issues = {"FHIR-100"}  # Only source started

        deps = extract_dependencies(issue, task_map, started_issues=started_issues)

        assert len(deps) == 1  # Kept because FHIR-200 not started

    def test_extract_dependencies_skip_unknown_issues(self) -> None:
        """Skip links to issues not in task_map."""
        links = [_make_link("Depends", outward_key="OTHER-999")]
        issue = _make_issue(key="FHIR-100", links=links)
        task_map = {"FHIR-200": "task-200-id"}  # OTHER-999 not in map

        deps = extract_dependencies(issue, task_map)

        assert len(deps) == 0


class TestBuildHierarchy:
    """Tests for build_hierarchy function."""

    def test_build_hierarchy_from_parent_field(self) -> None:
        """Parent field creates parent-child relationship."""
        issues = [
            _make_issue(key="EPIC-1"),
            _make_issue(key="FHIR-100", parent_key="EPIC-1"),
        ]

        hierarchy, warnings = build_hierarchy(issues)

        assert hierarchy["FHIR-100"].parent_key == "EPIC-1"
        assert "EPIC-1" not in hierarchy or hierarchy["EPIC-1"].parent_key is None

    def test_build_hierarchy_detects_sub_epic(self) -> None:
        """Sub-epic (epic with epic parent) generates warning."""
        issues = [
            _make_issue(key="EPIC-1", issue_type="Epic"),
            _make_issue(key="EPIC-2", issue_type="Epic", parent_key="EPIC-1"),
        ]

        hierarchy, warnings = build_hierarchy(issues)

        assert any(w.issue_key == "EPIC-2" for w in warnings)

    def test_build_hierarchy_from_parent_child_links(self) -> None:
        """'Parent of' / 'Child of' links create hierarchy."""
        links = [_make_link("Parent of", outward_key="FHIR-100")]
        issues = [
            _make_issue(key="EPIC-1", links=links),
            _make_issue(key="FHIR-100"),
        ]

        hierarchy, warnings = build_hierarchy(issues)

        assert hierarchy["FHIR-100"].parent_key == "EPIC-1"

    def test_build_hierarchy_no_orphans(self) -> None:
        """Issues with no parent have parent_key=None."""
        issues = [
            _make_issue(key="FHIR-100"),
            _make_issue(key="FHIR-200"),
        ]

        hierarchy, warnings = build_hierarchy(issues)

        assert hierarchy["FHIR-100"].parent_key is None
        assert hierarchy["FHIR-200"].parent_key is None


class TestExtractWorkers:
    """Tests for extract_workers function."""

    def test_extract_workers_from_worklogs(self) -> None:
        """Workers are extracted from worklog authors."""
        worklogs = [
            _make_worklog("user-1", "2024-01-15T10:00:00.000+0000", 3600, "User One"),
        ]
        issues = [_make_issue(worklogs=worklogs)]

        workers = extract_workers_with_no_hours(issues)

        assert "user-1" in workers
        assert workers["user-1"].jira_account_id == "user-1"
        assert workers["user-1"].name == "User One"

    def test_extract_workers_from_assignees(self) -> None:
        """Workers are extracted from assignees."""
        issues = [
            _make_issue(assignee_id="user-1", assignee_name="User One", worklogs=[])
        ]

        workers = extract_workers_with_no_hours(issues)

        assert "user-1" in workers
        assert workers["user-1"].name == "User One"

    def test_extract_workers_deduplicates(self) -> None:
        """Same user appearing multiple times only creates one worker."""
        worklogs1 = [
            _make_worklog("user-1", "2024-01-15T10:00:00.000+0000", 3600, "User One"),
        ]
        worklogs2 = [
            _make_worklog("user-1", "2024-01-16T10:00:00.000+0000", 7200, "User One"),
        ]
        issues = [
            _make_issue(key="FHIR-100", worklogs=worklogs1),
            _make_issue(key="FHIR-200", worklogs=worklogs2),
        ]

        workers = extract_workers_with_no_hours(issues)

        assert len([k for k in workers if k == "user-1"]) == 1


class TestCalculateHoursPerWorkday:
    """Tests for calculate_hours_per_workday function."""

    def test_calculate_hours_per_workday_single_day(self) -> None:
        """Single day of work calculates correctly."""
        worklogs = [
            _make_worklog("user-1", "2024-01-15T10:00:00.000+0000", 8 * 3600),  # 8h
        ]

        hours = calculate_hours_per_workday("user-1", worklogs)

        assert hours == 8.0

    def test_calculate_hours_per_workday_multiple_days(self) -> None:
        """Multiple days averages correctly."""
        worklogs = [
            _make_worklog("user-1", "2024-01-15T10:00:00.000+0000", 6 * 3600),  # 6h
            _make_worklog(
                "user-1", "2024-01-15T14:00:00.000+0000", 2 * 3600
            ),  # +2h same day
            _make_worklog("user-1", "2024-01-16T10:00:00.000+0000", 8 * 3600),  # 8h
        ]

        hours = calculate_hours_per_workday("user-1", worklogs)

        # Day 1: 6 + 2 = 8h, Day 2: 8h, Average: (8 + 8) / 2 = 8.0
        assert hours == 8.0

    def test_calculate_hours_per_workday_no_worklogs_for_user(self) -> None:
        """No worklogs for user returns None."""
        worklogs = [
            _make_worklog("user-2", "2024-01-15T10:00:00.000+0000", 8 * 3600),
        ]

        hours = calculate_hours_per_workday("user-1", worklogs)

        assert hours is None


class TestExtractTask:
    """Tests for extract_task function."""

    def test_extract_task_basic_fields(self) -> None:
        """Basic task extraction from issue."""
        issue = _make_issue(
            key="FHIR-100",
            summary="Test task",
            description="A description",
        )
        workers: dict[str, WorkerId] = {}
        server_url = "https://jira.example.com"

        task = extract_task(issue, workers, server_url)

        assert task.title == "Test task"
        assert task.description == "A description"
        assert task.jira_reference is not None
        assert task.jira_reference.issue_key.project_key == "FHIR"
        assert task.jira_reference.issue_key.issue_number == 100

    def test_extract_task_sets_jira_issue_type(self) -> None:
        """Task includes Jira issue type."""
        issue = _make_issue(issue_type="Bug")
        workers: dict[str, WorkerId] = {}
        server_url = "https://jira.example.com"

        task = extract_task(issue, workers, server_url)

        assert task.jira_issue_type == "Bug"

    def test_extract_task_with_parent(self) -> None:
        """Task with parent is extracted correctly."""
        issue = _make_issue(key="FHIR-100", parent_key="EPIC-1")
        workers: dict[str, WorkerId] = {}
        server_url = "https://jira.example.com"

        # Note: The actual parent Task would be passed, but we test the data extraction
        task = extract_task(issue, workers, server_url)

        # The parent relationship would be set separately by the caller
        assert task.title == "Test issue"

    def test_extract_task_preserves_estimate_and_points(self) -> None:
        """Duration distribution includes estimate and story points."""
        issue = _make_issue(
            original_estimate_seconds=3600 * 4,  # 4 hours
            story_points=5.0,
        )
        workers: dict[str, WorkerId] = {}
        server_url = "https://jira.example.com"

        task = extract_task(issue, workers, server_url)

        # The task should have JiraDurationDistribution with these values
        from fluxx.data.models import JiraDurationDistribution

        assert isinstance(task.duration_distribution, JiraDurationDistribution)
        assert task.duration_distribution.original_estimate_seconds == 3600 * 4
        assert task.duration_distribution.story_points == 5.0


class TestParseDatetime:
    """Tests for parse_jira_datetime helper."""

    def test_parse_datetime_with_positive_offset(self) -> None:
        """Parse datetime with positive timezone offset (+0000)."""
        result = parse_jira_datetime("2024-01-15T10:00:00.000+0000")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.tzinfo is None  # Should be naive

    def test_parse_datetime_with_negative_offset(self) -> None:
        """Parse datetime with negative timezone offset (-0500)."""
        result = parse_jira_datetime("2024-01-15T10:00:00.000-0500")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10  # Preserved as-is (not converted to UTC)
        assert result.tzinfo is None

    def test_parse_datetime_with_z_suffix(self) -> None:
        """Parse datetime with Z (UTC) suffix."""
        result = parse_jira_datetime("2024-01-15T10:00:00.000Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10

    def test_parse_datetime_with_z_suffix_no_milliseconds(self) -> None:
        """Parse datetime with Z suffix but no milliseconds."""
        result = parse_jira_datetime("2024-01-15T10:00:00Z")
        assert result.year == 2024
        assert result.hour == 10

    def test_parse_datetime_without_timezone_uses_server_timezone(self) -> None:
        """Parse datetime without timezone uses server_timezone fallback."""
        # When no timezone in string, server_timezone is applied then stripped
        result = parse_jira_datetime("2024-01-15T10:00:00", server_timezone="UTC")
        assert result.year == 2024
        assert result.hour == 10
        assert result.tzinfo is None

    def test_parse_datetime_with_milliseconds_no_timezone(self) -> None:
        """Parse datetime with milliseconds but no timezone."""
        result = parse_jira_datetime("2024-01-15T10:00:00.123")
        assert result.year == 2024
        assert result.hour == 10

    def test_parse_datetime_with_colon_offset_format(self) -> None:
        """Parse datetime with colon in offset (+00:00)."""
        result = parse_jira_datetime("2024-01-15T10:00:00+05:30")
        assert result.year == 2024
        assert result.hour == 10

    def test_parse_datetime_invalid_format_raises(self) -> None:
        """Invalid datetime format raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse datetime string"):
            parse_jira_datetime("not-a-datetime")


class TestExtractDependenciesEdgeCases:
    """Additional edge case tests for extract_dependencies."""

    def test_extract_dependencies_no_links(self) -> None:
        """Issue with no links returns empty list."""
        issue = _make_issue(key="FHIR-100", links=None)
        task_map = {"FHIR-200": "task-200-id"}

        deps = extract_dependencies(issue, task_map)

        assert len(deps) == 0

    def test_extract_dependencies_unrecognized_link_type(self) -> None:
        """Unrecognized link type is ignored."""
        links = [_make_link("Unknown Link Type", outward_key="FHIR-200")]
        issue = _make_issue(key="FHIR-100", links=links)
        task_map = {"FHIR-200": "task-200-id"}

        deps = extract_dependencies(issue, task_map)

        assert len(deps) == 0

    def test_extract_dependencies_link_without_target(self) -> None:
        """Link with neither inward nor outward issue is ignored."""
        # Create link with no target
        link = JiraIssueLink(
            id="link-1",
            link_type=JiraIssueLinkType(name="Depends"),
            outward_issue=None,
            inward_issue=None,
        )
        issue = _make_issue(key="FHIR-100", links=[link])
        task_map = {"FHIR-200": "task-200-id"}

        deps = extract_dependencies(issue, task_map)

        assert len(deps) == 0


class TestBuildHierarchyEdgeCases:
    """Additional edge case tests for build_hierarchy."""

    def test_build_hierarchy_child_of_link(self) -> None:
        """'Child of' inward link creates parent relationship."""
        # Create child-of link
        link = JiraIssueLink(
            id="link-1",
            link_type=JiraIssueLinkType(name="Child of"),
            inward_issue=JiraLinkedIssue(id="parent-id", key="EPIC-1"),
            outward_issue=None,
        )
        issues = [
            _make_issue(key="EPIC-1"),
            _make_issue(key="FHIR-100", links=[link]),
        ]

        hierarchy, warnings = build_hierarchy(issues)

        assert hierarchy["FHIR-100"].parent_key == "EPIC-1"

    def test_build_hierarchy_empty_links(self) -> None:
        """Issue with empty links list is handled."""
        issues = [
            _make_issue(key="FHIR-100", links=[]),
        ]

        hierarchy, warnings = build_hierarchy(issues)

        assert hierarchy["FHIR-100"].parent_key is None


class TestExtractCompletionEdgeCases:
    """Additional edge case tests for extract_completion."""

    def test_extract_completion_done_with_worklogs_no_assignee(self) -> None:
        """Done issue with worklogs but unknown worker creates placeholder."""
        worklogs = [
            _make_worklog("unknown-user", "2024-01-15T10:00:00.000+0000", 3600),
        ]
        issue = _make_issue(
            worklogs=worklogs,
            resolution_date="2024-01-20T12:00:00.000+0000",
        )
        workers: dict[str, WorkerId] = {}  # Unknown user not in workers

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, DoneCompletion)
        # Should have generated a placeholder worker ID
        assert result.completion.assignee is not None

    def test_extract_completion_started_no_known_assignee(self) -> None:
        """Started issue with worklogs from unknown worker creates placeholder."""
        worklogs = [
            _make_worklog("unknown-user", "2024-01-15T10:00:00.000+0000", 3600),
        ]
        issue = _make_issue(worklogs=worklogs)
        workers: dict[str, WorkerId] = {}  # Unknown user not in workers

        result = extract_completion(issue, workers)

        assert isinstance(result.completion, StartedCompletion)
        # Should have generated a placeholder worker ID
        assert result.completion.assignee is not None


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_get_earliest_worklog_time_empty_list_raises(self) -> None:
        """Empty worklog list raises ValueError."""
        with pytest.raises(ValueError, match="worklogs list must not be empty"):
            get_earliest_worklog_time([])

    def test_get_latest_worklog_time_empty_list_raises(self) -> None:
        """Empty worklog list raises ValueError."""
        with pytest.raises(ValueError, match="worklogs list must not be empty"):
            get_latest_worklog_time([])

    def test_get_earliest_worklog_time_returns_earliest(self) -> None:
        """Returns the earliest worklog start time."""
        worklogs = [
            _make_worklog("user-1", "2024-01-16T10:00:00.000+0000", 3600),
            _make_worklog("user-1", "2024-01-15T08:00:00.000+0000", 3600),  # earliest
            _make_worklog("user-1", "2024-01-15T14:00:00.000+0000", 3600),
        ]
        result = get_earliest_worklog_time(worklogs)
        assert result.day == 15
        assert result.hour == 8

    def test_get_latest_worklog_time_returns_latest(self) -> None:
        """Returns the latest worklog start time."""
        worklogs = [
            _make_worklog("user-1", "2024-01-16T10:00:00.000+0000", 3600),  # latest
            _make_worklog("user-1", "2024-01-15T08:00:00.000+0000", 3600),
            _make_worklog("user-1", "2024-01-15T14:00:00.000+0000", 3600),
        ]
        result = get_latest_worklog_time(worklogs)
        assert result.day == 16
        assert result.hour == 10

    def test_calculate_hours_per_workday_empty_worklogs(self) -> None:
        """Empty worklogs list returns None."""
        result = calculate_hours_per_workday("user-1", [])
        assert result is None
