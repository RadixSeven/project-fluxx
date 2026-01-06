"""Tests for Jira import orchestration."""

from datetime import datetime
from unittest.mock import MagicMock

from fluxx.data.id_generation import generate_worker_id
from fluxx.data.json_types import JsonObject
from fluxx.data.models import (
    DAG,
    JiraDurationDistribution,
    Project,
    ProjectMetadata,
    ShiftedLognormal,
    Worker,
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
from fluxx.jira.distributions import EstimateBin
from fluxx.jira.importer import (
    ImportProgress,
    ImportResult,
    ImportWarningFluxx,
    _build_duration_distribution,
    _build_project,
    _collect_all_worklogs,
    _create_history_entries,
    extract_raw_estimate_data,
    fetch_and_validate_issues,
    import_from_jira,
)
from fluxx.jira.models import (
    JiraConfig,
    JiraDurationHistoryEntry,
    JiraIssueKey,
    JiraSyncMetadata,
)


def make_issue(
    key: str = "TEST-1",
    summary: str = "Test issue",
    issue_type: str = "Story",
    resolution_date: str | None = None,
    worklogs: list[JiraWorklogEntry] | None = None,
    assignee: JiraUser | None = None,
    parent_key: str | None = None,
    original_estimate_seconds: int | None = None,
    story_points: float | None = None,
    issue_id: str = "12345",
    issuelinks: list[JiraIssueLink] | None = None,
) -> JiraIssueResponse:
    """Create a test JiraIssueResponse."""
    worklog = None
    if worklogs is not None:
        worklog = JiraWorklog(
            start_at=0,
            max_results=len(worklogs),
            total=len(worklogs),
            worklogs=worklogs,
        )

    timetracking = None
    if original_estimate_seconds is not None:
        timetracking = JiraTimeTracking(
            original_estimate_seconds=original_estimate_seconds
        )

    parent = None
    if parent_key:
        parent = JiraParentRef(id="99999", key=parent_key)

    fields = JiraIssueFields(
        summary=summary,
        description="Test description",
        issuetype=JiraIssueType(id="10001", name=issue_type),
        status=JiraStatus(id="1", name="Open"),
        assignee=assignee,
        parent=parent,
        issuelinks=issuelinks if issuelinks is not None else [],
        resolutiondate=resolution_date,
        worklog=worklog,
        timetracking=timetracking,
        story_points=story_points,
    )

    return JiraIssueResponse(id=issue_id, key=key, fields=fields)


def make_worklog(
    account_id: str = "user1",
    display_name: str = "User One",
    time_seconds: int = 3600,
    started: str = "2024-01-15T10:00:00.000+0000",
) -> JiraWorklogEntry:
    """Create a test worklog entry."""
    return JiraWorklogEntry(
        author=JiraUser(account_id=account_id, display_name=display_name),
        time_spent_seconds=time_seconds,
        started=started,
    )


class TestCollectAllWorklogs:
    """Tests for _collect_all_worklogs."""

    def test_empty_issues(self) -> None:
        """Empty issue list returns empty worklogs."""
        result = _collect_all_worklogs([])
        assert result == []

    def test_issues_without_worklogs(self) -> None:
        """Issues without worklogs return empty list."""
        issue = make_issue()
        result = _collect_all_worklogs([issue])
        assert result == []

    def test_issues_with_worklogs(self) -> None:
        """Worklogs are collected from all issues."""
        w1 = make_worklog(account_id="user1", time_seconds=3600)
        w2 = make_worklog(account_id="user2", time_seconds=7200)
        issue1 = make_issue(key="TEST-1", worklogs=[w1])
        issue2 = make_issue(key="TEST-2", worklogs=[w2])

        result = _collect_all_worklogs([issue1, issue2])
        assert len(result) == 2
        assert w1 in result
        assert w2 in result


class TestCreateHistoryEntries:
    """Tests for _create_history_entries."""

    def test_empty_issues(self) -> None:
        """Empty issue list returns empty entries."""
        result = _create_history_entries([], {}, "https://jira.example.com", "UTC")
        assert result == []

    def test_not_done_issues_excluded(self) -> None:
        """Issues not in Done state are excluded."""
        issue = make_issue()  # Not resolved
        result = _create_history_entries([issue], {}, "https://jira.example.com", "UTC")
        assert result == []

    def test_done_with_work_included(self) -> None:
        """Done issues with actual work logged are included."""
        worklog = make_worklog(time_seconds=7200)
        issue = make_issue(
            key="TEST-1",
            resolution_date="2024-01-15T12:00:00.000+0000",
            worklogs=[worklog],
            original_estimate_seconds=14400,
        )

        result = _create_history_entries([issue], {}, "https://jira.example.com", "UTC")

        assert len(result) == 1
        entry = result[0]
        assert str(entry.issue_key) == "TEST-1"
        assert entry.original_estimate_seconds == 14400
        assert entry.total_logged_time_seconds == 7200
        assert entry.worker_jira_id == "user1"
        assert entry.issue_type == "Story"


class TestBuildDurationDistribution:
    """Tests for _build_duration_distribution."""

    def test_with_bins_and_estimate(self) -> None:
        """Uses bin distribution when bins and estimate available."""
        dist = ShiftedLognormal(min=1.0, mode=2.0, percentile_95=5.0)
        bin_ = EstimateBin(
            center_estimate=4.0,
            lower_bound=2.0,
            upper_bound=6.0,
            samples=[3.0, 4.0, 5.0],
            distribution=dist,
        )
        issue = make_issue(original_estimate_seconds=14400)  # 4 hours

        result = _build_duration_distribution(issue, [bin_], None)
        assert result == dist

    def test_with_fallback(self) -> None:
        """Uses fallback distribution when no bins or estimate."""
        fallback = ShiftedLognormal(min=0.5, mode=1.5, percentile_95=4.0)
        issue = make_issue()

        result = _build_duration_distribution(issue, [], fallback)
        assert result == fallback

    def test_returns_jira_distribution(self) -> None:
        """Returns JiraDurationDistribution when no fitted distribution."""
        issue = make_issue(
            original_estimate_seconds=7200,
            story_points=3.0,
        )

        result = _build_duration_distribution(issue, [], None)
        assert isinstance(result, JiraDurationDistribution)
        assert result.original_estimate_seconds == 7200
        assert result.story_points == 3.0


class TestBuildProject:
    """Tests for _build_project."""

    def test_single_issue(self) -> None:
        """Build project with a single issue."""
        worker = Worker(
            id=generate_worker_id(),
            name="User One",
            jira_account_id="user1",
            hours_per_workday=8.0,
        )
        workers = {"user1": worker}

        issue = make_issue(key="TEST-1", summary="Test Task")
        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        project, warnings = _build_project(
            issues=[issue],
            workers=workers,
            config=config,
            bins=[],
            fallback=None,
            project_name="Test Project",
        )

        assert project.metadata.name == "Test Project"
        assert len(project.workers) == 1
        assert len(project.dag.node_map) == 1
        assert len(project.persistent_tasks) == 1

    def test_with_hierarchy(self) -> None:
        """Build project with parent-child relationship."""
        worker = Worker(
            id=generate_worker_id(),
            name="User One",
            jira_account_id="user1",
            hours_per_workday=8.0,
        )
        workers = {"user1": worker}

        parent_issue = make_issue(key="TEST-1", summary="Parent Task")
        child_issue = make_issue(
            key="TEST-2", summary="Child Task", parent_key="TEST-1"
        )

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        project, warnings = _build_project(
            issues=[parent_issue, child_issue],
            workers=workers,
            config=config,
            bins=[],
            fallback=None,
            project_name="Test Project",
        )

        assert len(project.dag.node_map) == 2
        # Find the child task and verify it has a parent
        child_task = None
        dag_version = project.dag.current_version_id
        for pt in project.persistent_tasks.values():
            task = pt.versions.get(dag_version)
            if task and task.title == "Child Task":
                child_task = task
                break

        assert child_task is not None
        assert child_task.parent_id is not None


class TestImportFromJira:
    """Tests for import_from_jira."""

    def test_basic_import(self) -> None:
        """Test basic import flow."""
        mock_client = MagicMock()

        # Create test issue data as dict (what the API returns)
        issue_dict = {
            "id": "12345",
            "key": "TEST-1",
            "fields": {
                "summary": "Test Issue",
                "description": "Description",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }
        mock_client.search.return_value = iter([issue_dict])

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        result = import_from_jira(
            client=mock_client,
            jql="project = TEST",
            config=config,
            project_name="Test Project",
        )

        assert isinstance(result, ImportResult)
        assert result.project.metadata.name == "Test Project"
        assert len(result.project.dag.node_map) == 1

    def test_import_with_progress_callback(self) -> None:
        """Progress callback is called during import."""
        mock_client = MagicMock()
        mock_client.search.return_value = iter([])

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        progress_updates: list[ImportProgress] = []

        def callback(progress: ImportProgress) -> None:
            progress_updates.append(progress)

        import_from_jira(
            client=mock_client,
            jql="project = TEST",
            config=config,
            project_name="Test Project",
            progress_callback=callback,
        )

        assert len(progress_updates) > 0
        phases = [p.current_phase for p in progress_updates]
        assert "fetching_issues" in phases
        assert "building_project" in phases


class TestFetchAndValidateIssues:
    """Tests for fetch_and_validate_issues."""

    def test_valid_issues(self) -> None:
        """Valid issues are parsed successfully."""
        mock_client = MagicMock()
        issue_dict = {
            "id": "12345",
            "key": "TEST-1",
            "fields": {
                "summary": "Test Issue",
                "description": "Description",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }
        mock_client.search.return_value = iter([issue_dict])

        issues, warnings = fetch_and_validate_issues(mock_client, "project = TEST")

        assert len(issues) == 1
        assert issues[0].key == "TEST-1"
        assert len(warnings) == 0

    def test_invalid_issue_creates_warning(self) -> None:
        """Invalid issues create warnings."""
        mock_client = MagicMock()
        # Invalid issue - missing required fields
        invalid_dict = {"key": "TEST-1", "fields": {}}
        mock_client.search.return_value = iter([invalid_dict])

        issues, warnings = fetch_and_validate_issues(mock_client, "project = TEST")

        assert len(issues) == 0
        assert len(warnings) == 1
        assert warnings[0].issue_key == "TEST-1"
        assert "Validation error" in warnings[0].message

    def test_invalid_issue_without_key(self) -> None:
        """Invalid issue without key uses 'unknown'."""
        mock_client = MagicMock()
        invalid_dict: JsonObject = {"fields": {}}  # No key field
        mock_client.search.return_value = iter([invalid_dict])

        issues, warnings = fetch_and_validate_issues(mock_client, "project = TEST")

        assert len(issues) == 0
        assert len(warnings) == 1
        assert warnings[0].issue_key == "unknown"


class TestImportProgress:
    """Tests for ImportProgress dataclass."""

    def test_default_values(self) -> None:
        """ImportProgress has correct defaults."""
        progress = ImportProgress()
        assert progress.total_issues == 0
        assert progress.processed_issues == 0
        assert progress.current_phase == "initializing"


class TestImportWarning:
    """Tests for ImportWarning dataclass."""

    def test_creation(self) -> None:
        """ImportWarning can be created."""
        warning = ImportWarningFluxx(issue_key="TEST-1", message="Test warning")
        assert warning.issue_key == "TEST-1"
        assert warning.message == "Test warning"


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_default_lists(self) -> None:
        """ImportResult has empty default lists."""
        from fluxx.data.id_generation import generate_dag_id, generate_dag_version_id

        project = Project(
            metadata=ProjectMetadata(
                name="Test",
                created=datetime.now().astimezone(),
                last_modified=datetime.now().astimezone(),
            ),
            dag=DAG(
                id=generate_dag_id(),
                current_version_id=generate_dag_version_id(),
            ),
        )
        result = ImportResult(project=project)
        assert result.warnings == []
        assert result.history_entries == []


class TestBuildProjectWithDependencies:
    """Tests for _build_project with issue links (dependencies)."""

    def test_with_issue_links(self) -> None:
        """Build project with issue dependencies via links."""
        worker = Worker(
            id=generate_worker_id(),
            name="User One",
            jira_account_id="user1",
            hours_per_workday=8.0,
        )
        workers = {"user1": worker}

        # Create a "blocks" link on TEST-2 with inward_issue = TEST-1
        # This represents: TEST-1 blocks TEST-2, so TEST-2 depends on TEST-1
        issue_link = JiraIssueLink(
            id="1001",
            link_type=JiraIssueLinkType(name="Blocks", inward="is blocked by"),
            inward_issue=JiraLinkedIssue(id="11111", key="TEST-1"),
        )

        # Blocker issue (no link on it)
        blocker_issue = make_issue(
            key="TEST-1",
            summary="Blocker Task",
            issue_id="11111",
        )
        # Blocked issue with the inward "Blocks" link
        blocked_issue = make_issue(
            key="TEST-2",
            summary="Blocked Task",
            issue_id="22222",
            issuelinks=[issue_link],
        )

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        project, warnings = _build_project(
            issues=[blocker_issue, blocked_issue],
            workers=workers,
            config=config,
            bins=[],
            fallback=None,
            project_name="Test Project",
        )

        assert len(project.dag.node_map) == 2
        # Verify dependencies were created
        dag_version = project.dag.current_version_id
        blocked_task = None
        for pt in project.persistent_tasks.values():
            task = pt.versions.get(dag_version)
            if task and task.title == "Blocked Task":
                blocked_task = task
                break

        assert blocked_task is not None
        assert len(blocked_task.dependencies) > 0


class TestImportWithCompletedIssues:
    """Tests for import_from_jira with completed issues."""

    def test_import_with_worklogs_and_distribution_fitting(self) -> None:
        """Import with completed issues triggers distribution fitting."""
        mock_client = MagicMock()

        # Create multiple completed issues with worklogs for distribution fitting
        issues = []
        for i in range(5):
            issue_dict = {
                "id": str(10000 + i),
                "key": f"TEST-{i + 1}",
                "fields": {
                    "summary": f"Test Issue {i + 1}",
                    "description": "Description",
                    "issuetype": {"id": "10001", "name": "Story"},
                    "status": {"id": "1", "name": "Done"},
                    "assignee": {
                        "accountId": "user1",
                        "displayName": "User One",
                        "active": True,
                    },
                    "parent": None,
                    "issuelinks": [],
                    "resolutiondate": "2024-01-15T12:00:00.000+0000",
                    "worklog": {
                        "startAt": 0,
                        "maxResults": 1,
                        "total": 1,
                        "worklogs": [
                            {
                                "id": f"wl-{i}",
                                "author": {
                                    "accountId": "user1",
                                    "displayName": "User One",
                                    "active": True,
                                },
                                "started": "2024-01-14T10:00:00.000+0000",
                                "timeSpent": "2h",
                                "timeSpentSeconds": 7200 + i * 1000,
                            }
                        ],
                    },
                    "timetracking": {
                        "originalEstimate": "4h",
                        "originalEstimateSeconds": 14400 + i * 500,
                    },
                },
            }
            issues.append(issue_dict)

        mock_client.search.return_value = iter(issues)

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        result = import_from_jira(
            client=mock_client,
            jql="project = TEST",
            config=config,
            project_name="Test Project",
            min_samples_for_bins=3,  # Lower threshold to trigger bin fitting
        )

        assert isinstance(result, ImportResult)
        assert len(result.project.dag.node_map) == 5
        assert len(result.history_entries) == 5
        # Workers should have updated hours_per_workday
        assert len(result.project.workers) == 1


class TestCreateHistoryEntriesWithWorkers:
    """Tests for _create_history_entries with workers mapping."""

    def test_with_workers_mapping(self) -> None:
        """History entries work with workers that have jira_account_id."""
        worker = Worker(
            id=generate_worker_id(),
            name="User One",
            jira_account_id="user1",
            hours_per_workday=8.0,
        )
        workers = {"user1": worker}

        worklog = make_worklog(time_seconds=7200)
        issue = make_issue(
            key="TEST-1",
            resolution_date="2024-01-15T12:00:00.000+0000",
            worklogs=[worklog],
            original_estimate_seconds=14400,
        )

        result = _create_history_entries(
            [issue], workers, "https://jira.example.com", "UTC"
        )

        assert len(result) == 1
        assert result[0].worker_jira_id == "user1"


class TestFetchAndValidateIssuesNonStringKey:
    """Tests for fetch_and_validate_issues with non-string key."""

    def test_non_string_key_uses_unknown(self) -> None:
        """Non-string key in invalid issue uses 'unknown'."""
        mock_client = MagicMock()
        # Invalid issue with non-string key (e.g., integer or nested object)
        invalid_dict = {"key": 12345, "fields": {}}  # key is an int, not str
        mock_client.search.return_value = iter([invalid_dict])

        issues, warnings = fetch_and_validate_issues(mock_client, "project = TEST")

        assert len(issues) == 0
        assert len(warnings) == 1
        assert warnings[0].issue_key == "unknown"


class TestBuildProjectWithHierarchyWarning:
    """Tests for _build_project with hierarchy warnings."""

    def test_sub_epic_generates_warning(self) -> None:
        """Sub-epic (epic with epic parent) generates hierarchy warning."""
        worker = Worker(
            id=generate_worker_id(),
            name="User One",
            jira_account_id="user1",
            hours_per_workday=8.0,
        )
        workers = {"user1": worker}

        # Create parent Epic
        parent_epic = make_issue(
            key="EPIC-1",
            summary="Parent Epic",
            issue_type="Epic",
            issue_id="11111",
        )
        # Create sub-epic (Epic with Epic parent)
        sub_epic = make_issue(
            key="EPIC-2",
            summary="Sub Epic",
            issue_type="Epic",
            issue_id="22222",
            parent_key="EPIC-1",
        )

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        project, warnings = _build_project(
            issues=[parent_epic, sub_epic],
            workers=workers,
            config=config,
            bins=[],
            fallback=None,
            project_name="Test Project",
        )

        assert len(project.dag.node_map) == 2
        # Should have a hierarchy warning for sub-epic
        assert len(warnings) == 1
        assert "Sub-epic" in warnings[0].message
        assert "EPIC-2" in warnings[0].issue_key


class TestExtractRawEstimateData:
    """Tests for extract_raw_estimate_data."""

    def test_extracts_estimate_and_actual_hours(self) -> None:
        """Converts estimate to hours and preserves actual seconds."""
        entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey.from_string("TEST-1"),
            original_estimate_seconds=7200,
            total_logged_time_seconds=3600,
            worker_jira_id="user1",
            issue_type="Story",
        )

        result = extract_raw_estimate_data([entry])

        assert result == [(2.0, 1.0)]

    def test_handles_missing_estimate_or_actual(self) -> None:
        """Retains None when estimate or actual is missing."""
        entries = [
            JiraDurationHistoryEntry(
                server_url="https://jira.example.com",
                issue_key=JiraIssueKey.from_string("TEST-2"),
                original_estimate_seconds=None,
                total_logged_time_seconds=1800,
                worker_jira_id=None,
                issue_type="Bug",
            ),
            JiraDurationHistoryEntry(
                server_url="https://jira.example.com",
                issue_key=JiraIssueKey.from_string("TEST-3"),
                original_estimate_seconds=3600,
                total_logged_time_seconds=None,
                worker_jira_id=None,
                issue_type="Task",
            ),
        ]

        result = extract_raw_estimate_data(entries)

        assert result == [(None, 0.5), (1.0, None)]
