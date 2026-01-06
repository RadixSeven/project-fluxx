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
    build_children_jql,
    extract_raw_estimate_data,
    fetch_all_issues_with_children,
    fetch_and_validate_issues,
    get_children_from_links,
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


class TestEndToEndImport:
    """End-to-end integration tests for Jira import."""

    def test_e2e_import_epic_with_hierarchy(self) -> None:
        """Full E2E test: import epic with stories and verify hierarchy."""
        mock_client = MagicMock()

        # Create a realistic epic hierarchy:
        # EPIC-1 (Epic)
        # ├── STORY-1 (Story under epic)
        # │   └── SUB-1 (Subtask under story)
        # └── STORY-2 (Story under epic with worklogs)
        epic = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {
                "summary": "Main Epic",
                "description": "The main epic for testing",
                "issuetype": {"id": "10000", "name": "Epic"},
                "status": {"id": "1", "name": "In Progress"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        story1 = {
            "id": "10002",
            "key": "STORY-1",
            "fields": {
                "summary": "First Story",
                "description": "Story under the epic",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "To Do"},
                "assignee": None,
                "parent": {"id": "10001", "key": "EPIC-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": {"originalEstimateSeconds": 28800},  # 8 hours
            },
        }

        subtask1 = {
            "id": "10003",
            "key": "SUB-1",
            "fields": {
                "summary": "Subtask under Story",
                "description": "Subtask for first story",
                "issuetype": {"id": "10002", "name": "Sub-task"},
                "status": {"id": "1", "name": "To Do"},
                "assignee": None,
                "parent": {"id": "10002", "key": "STORY-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": {"originalEstimateSeconds": 14400},  # 4 hours
            },
        }

        story2 = {
            "id": "10004",
            "key": "STORY-2",
            "fields": {
                "summary": "Second Story with Worklogs",
                "description": "Completed story",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "3", "name": "Done"},
                "assignee": {
                    "accountId": "user-alice",
                    "displayName": "Alice Developer",
                    "active": True,
                },
                "parent": {"id": "10001", "key": "EPIC-1"},
                "issuelinks": [],
                "resolutiondate": "2024-06-15T12:00:00.000+0000",
                "worklog": {
                    "startAt": 0,
                    "maxResults": 2,
                    "total": 2,
                    "worklogs": [
                        {
                            "id": "wl-1",
                            "author": {
                                "accountId": "user-alice",
                                "displayName": "Alice Developer",
                                "active": True,
                            },
                            "started": "2024-06-14T09:00:00.000+0000",
                            "timeSpent": "4h",
                            "timeSpentSeconds": 14400,
                        },
                        {
                            "id": "wl-2",
                            "author": {
                                "accountId": "user-alice",
                                "displayName": "Alice Developer",
                                "active": True,
                            },
                            "started": "2024-06-15T09:00:00.000+0000",
                            "timeSpent": "2h",
                            "timeSpentSeconds": 7200,
                        },
                    ],
                },
                "timetracking": {"originalEstimateSeconds": 21600},  # 6 hours
            },
        }

        mock_client.search.return_value = iter([epic, story1, subtask1, story2])

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
            project_name="E2E Test Project",
        )

        # Verify result structure
        assert isinstance(result, ImportResult)
        assert result.project.metadata.name == "E2E Test Project"

        # Verify all 4 tasks created
        assert len(result.project.dag.node_map) == 4

        # Verify workers extracted from worklogs
        assert len(result.project.workers) == 1
        worker = result.project.workers[0]
        assert worker.name == "Alice Developer"
        assert worker.jira_account_id == "user-alice"

        # Note: jira_config is not set by the importer - it uses the config passed in
        # but doesn't copy it to the project (this could be improved in the future)

        # Verify history entries for completed story
        assert len(result.history_entries) == 1
        history = result.history_entries[0]
        assert history.issue_key.project_key == "STORY"
        assert history.issue_key.issue_number == 2

        # Verify hierarchy by checking parent-child relationships
        tasks = {}
        for _node_id, persistent_id in result.project.dag.node_map.items():
            if persistent_id in result.project.persistent_tasks:
                ptask = result.project.persistent_tasks[persistent_id]
                task = ptask.versions[result.project.dag.current_version_id]
                if task.jira_reference is not None:
                    tasks[str(task.jira_reference.issue_key)] = task

        # Epic should have no parent
        assert tasks["EPIC-1"].parent_id is None

        # Stories should have epic as parent
        assert tasks["STORY-1"].parent_id is not None
        assert tasks["STORY-2"].parent_id is not None

        # Subtask should have story as parent
        assert tasks["SUB-1"].parent_id is not None

        # Verify Jira references
        for task in tasks.values():
            assert task.jira_reference is not None
            assert task.jira_reference.server_url == "https://jira.example.com"

        # Verify issue types
        assert tasks["EPIC-1"].jira_issue_type == "Epic"
        assert tasks["STORY-1"].jira_issue_type == "Story"
        assert tasks["SUB-1"].jira_issue_type == "Sub-task"
        assert tasks["STORY-2"].jira_issue_type == "Story"

    def test_e2e_import_generates_progress_callbacks(self) -> None:
        """E2E test verifies progress callbacks are called with phases."""
        mock_client = MagicMock()
        mock_client.search.return_value = iter(
            [
                {
                    "id": "10001",
                    "key": "TEST-1",
                    "fields": {
                        "summary": "Test Issue",
                        "description": "Test",
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
            ]
        )

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        progress_updates: list[ImportProgress] = []

        result = import_from_jira(
            client=mock_client,
            jql="project = TEST",
            config=config,
            project_name="Progress Test",
            progress_callback=lambda p: progress_updates.append(p),
        )

        assert isinstance(result, ImportResult)

        # Verify all expected phases were reported
        phases = [p.current_phase for p in progress_updates]
        assert "fetching_issues" in phases
        assert "building_project" in phases

    def test_e2e_fetch_and_validate_collects_warnings(self) -> None:
        """E2E test verifies fetch_and_validate_issues collects validation warnings."""
        mock_client = MagicMock()

        # Valid issue
        valid_issue = {
            "id": "10001",
            "key": "TEST-1",
            "fields": {
                "summary": "Valid Issue",
                "description": "Test",
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

        # Invalid issue (missing required fields)
        invalid_issue = {
            "id": "10002",
            "key": "TEST-2",
            "fields": {
                # Missing issuetype and status
                "summary": "Invalid Issue",
            },
        }

        mock_client.search.return_value = iter([valid_issue, invalid_issue])

        # Use fetch_and_validate_issues which handles validation errors gracefully
        issues, warnings = fetch_and_validate_issues(mock_client, "project = TEST")

        # Only valid issue should be returned
        assert len(issues) == 1
        assert issues[0].key == "TEST-1"

        # Should have a warning about the invalid issue
        assert len(warnings) >= 1
        warning_keys = [w.issue_key for w in warnings]
        assert "TEST-2" in warning_keys


class TestGetChildrenFromLinks:
    """Tests for get_children_from_links function."""

    def test_empty_issues(self) -> None:
        """Empty issue list returns empty set."""
        result = get_children_from_links([], set())
        assert result == set()

    def test_no_links(self) -> None:
        """Issues without links return empty set."""
        issue = make_issue(key="TEST-1")
        result = get_children_from_links([issue], set())
        assert result == set()

    def test_parent_of_outward_link(self) -> None:
        """'Parent of' outward link identifies child."""
        parent_of_link = JiraIssueLink(
            id="1001",
            link_type=JiraIssueLinkType(name="Parent of"),
            outward_issue=JiraLinkedIssue(id="22222", key="TEST-2"),
        )
        issue = make_issue(key="TEST-1", issuelinks=[parent_of_link])

        result = get_children_from_links([issue], set())

        assert result == {"TEST-2"}

    def test_child_of_inward_link(self) -> None:
        """'Child of' inward link identifies child."""
        child_of_link = JiraIssueLink(
            id="1001",
            link_type=JiraIssueLinkType(name="Child of"),
            inward_issue=JiraLinkedIssue(id="33333", key="TEST-3"),
        )
        issue = make_issue(key="TEST-1", issuelinks=[child_of_link])

        result = get_children_from_links([issue], set())

        assert result == {"TEST-3"}

    def test_excludes_already_fetched(self) -> None:
        """Already fetched issues are excluded."""
        parent_of_link = JiraIssueLink(
            id="1001",
            link_type=JiraIssueLinkType(name="Parent of"),
            outward_issue=JiraLinkedIssue(id="22222", key="TEST-2"),
        )
        issue = make_issue(key="TEST-1", issuelinks=[parent_of_link])

        result = get_children_from_links([issue], {"TEST-2"})

        assert result == set()

    def test_multiple_children_from_multiple_issues(self) -> None:
        """Multiple children from multiple issues are collected."""
        link1 = JiraIssueLink(
            id="1001",
            link_type=JiraIssueLinkType(name="Parent of"),
            outward_issue=JiraLinkedIssue(id="22222", key="CHILD-1"),
        )
        link2 = JiraIssueLink(
            id="1002",
            link_type=JiraIssueLinkType(name="Parent of"),
            outward_issue=JiraLinkedIssue(id="33333", key="CHILD-2"),
        )
        issue1 = make_issue(key="PARENT-1", issuelinks=[link1])
        issue2 = make_issue(key="PARENT-2", issuelinks=[link2])

        result = get_children_from_links([issue1, issue2], set())

        assert result == {"CHILD-1", "CHILD-2"}


class TestBuildChildrenJql:
    """Tests for build_children_jql function."""

    def test_single_key(self) -> None:
        """JQL for single parent key."""
        result = build_children_jql(["EPIC-1"])
        assert result == '"Epic Link" in ("EPIC-1") OR parent in ("EPIC-1")'

    def test_multiple_keys(self) -> None:
        """JQL for multiple parent keys."""
        result = build_children_jql(["EPIC-1", "STORY-2", "TASK-3"])
        expected = (
            '"Epic Link" in ("EPIC-1", "STORY-2", "TASK-3") OR '
            'parent in ("EPIC-1", "STORY-2", "TASK-3")'
        )
        assert result == expected


class TestFetchAllIssuesWithChildren:
    """Tests for fetch_all_issues_with_children function."""

    def test_no_children(self) -> None:
        """Issues without children are returned directly."""
        mock_client = MagicMock()

        issue_dict = {
            "id": "12345",
            "key": "EPIC-1",
            "fields": {
                "summary": "Epic without children",
                "description": "Test",
                "issuetype": {"id": "10000", "name": "Epic"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        # First search returns the epic, second search (for children) returns empty
        mock_client.search.side_effect = [
            iter([issue_dict]),  # Initial query
            iter([]),  # Children query
        ]

        result = fetch_all_issues_with_children(mock_client, 'key = "EPIC-1"')

        assert len(result) == 1
        assert result[0].key == "EPIC-1"

    def test_fetches_direct_children(self) -> None:
        """Fetches children via Epic Link and parent fields."""
        mock_client = MagicMock()

        epic_dict = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {
                "summary": "Epic",
                "description": "Test",
                "issuetype": {"id": "10000", "name": "Epic"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        child_dict = {
            "id": "10002",
            "key": "STORY-1",
            "fields": {
                "summary": "Story under epic",
                "description": "Test",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": {"id": "10001", "key": "EPIC-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        # Sequence of search calls
        mock_client.search.side_effect = [
            iter([epic_dict]),  # Initial query
            iter([child_dict]),  # Children of epic
            iter([]),  # Children of story (none)
        ]

        result = fetch_all_issues_with_children(mock_client, 'key = "EPIC-1"')

        assert len(result) == 2
        keys = {issue.key for issue in result}
        assert keys == {"EPIC-1", "STORY-1"}

    def test_fetches_nested_children(self) -> None:
        """Fetches multiple levels of children."""
        mock_client = MagicMock()

        epic_dict = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {
                "summary": "Epic",
                "description": "Test",
                "issuetype": {"id": "10000", "name": "Epic"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        story_dict = {
            "id": "10002",
            "key": "STORY-1",
            "fields": {
                "summary": "Story",
                "description": "Test",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": {"id": "10001", "key": "EPIC-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        subtask_dict = {
            "id": "10003",
            "key": "SUB-1",
            "fields": {
                "summary": "Subtask",
                "description": "Test",
                "issuetype": {"id": "10002", "name": "Sub-task", "subtask": True},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": {"id": "10002", "key": "STORY-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        mock_client.search.side_effect = [
            iter([epic_dict]),  # Initial query
            iter([story_dict]),  # Children of epic
            iter([subtask_dict]),  # Children of story
            iter([]),  # Children of subtask (none)
        ]

        result = fetch_all_issues_with_children(mock_client, 'key = "EPIC-1"')

        assert len(result) == 3
        keys = {issue.key for issue in result}
        assert keys == {"EPIC-1", "STORY-1", "SUB-1"}

    def test_deduplicates_issues(self) -> None:
        """Duplicate issues from different queries are deduplicated."""
        mock_client = MagicMock()

        epic_dict = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {
                "summary": "Epic",
                "description": "Test",
                "issuetype": {"id": "10000", "name": "Epic"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        story_dict = {
            "id": "10002",
            "key": "STORY-1",
            "fields": {
                "summary": "Story",
                "description": "Test",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": {"id": "10001", "key": "EPIC-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        # Simulate story appearing in both initial and children query
        mock_client.search.side_effect = [
            iter([epic_dict, story_dict]),  # Initial query returns both
            iter([story_dict]),  # Children query also returns story (duplicate)
            iter([]),  # Children of story (none)
        ]

        result = fetch_all_issues_with_children(mock_client, "project = TEST")

        assert len(result) == 2  # Deduplicated
        keys = {issue.key for issue in result}
        assert keys == {"EPIC-1", "STORY-1"}

    def test_fetches_children_from_links(self) -> None:
        """Fetches children referenced via 'parent of' links."""
        mock_client = MagicMock()

        parent_of_link_dict = {
            "id": "1001",
            "type": {"name": "Parent of"},
            "outwardIssue": {"id": "10002", "key": "CHILD-1"},
        }

        parent_dict = {
            "id": "10001",
            "key": "PARENT-1",
            "fields": {
                "summary": "Parent with link",
                "description": "Test",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [parent_of_link_dict],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        child_dict = {
            "id": "10002",
            "key": "CHILD-1",
            "fields": {
                "summary": "Child via link",
                "description": "Test",
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

        # Search returns parent, then children query returns empty,
        # but get_issue is called to fetch the linked child
        mock_client.search.side_effect = [
            iter([parent_dict]),  # Initial query
            iter([]),  # Children via Epic Link/parent (none)
            iter([]),  # Children of linked child (none)
        ]
        mock_client.get_issue.return_value = child_dict

        result = fetch_all_issues_with_children(mock_client, 'key = "PARENT-1"')

        assert len(result) == 2
        keys = {issue.key for issue in result}
        assert keys == {"PARENT-1", "CHILD-1"}

    def test_handles_get_issue_failure_gracefully(self) -> None:
        """get_issue failure for linked child is handled gracefully."""
        mock_client = MagicMock()

        parent_of_link_dict = {
            "id": "1001",
            "type": {"name": "Parent of"},
            "outwardIssue": {"id": "10002", "key": "INACCESSIBLE-1"},
        }

        parent_dict = {
            "id": "10001",
            "key": "PARENT-1",
            "fields": {
                "summary": "Parent with link to inaccessible child",
                "description": "Test",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [parent_of_link_dict],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        mock_client.search.side_effect = [
            iter([parent_dict]),  # Initial query
            iter([]),  # Children via Epic Link/parent (none)
        ]
        # get_issue fails (issue doesn't exist or not accessible)
        mock_client.get_issue.side_effect = Exception("Issue not found")

        result = fetch_all_issues_with_children(mock_client, 'key = "PARENT-1"')

        # Only parent should be returned, inaccessible child is skipped
        assert len(result) == 1
        assert result[0].key == "PARENT-1"

    def test_progress_callback_called(self) -> None:
        """Progress callback is called during fetching."""
        mock_client = MagicMock()

        issue_dict = {
            "id": "12345",
            "key": "TEST-1",
            "fields": {
                "summary": "Test",
                "description": "Test",
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

        mock_client.search.side_effect = [
            iter([issue_dict]),
            iter([]),
        ]

        progress_calls: list[tuple[str, int, int]] = []

        def progress_callback(phase: str, processed: int, total: int) -> None:
            progress_calls.append((phase, processed, total))

        fetch_all_issues_with_children(mock_client, "project = TEST", progress_callback)

        assert len(progress_calls) > 0
        phases = [call[0] for call in progress_calls]
        assert "fetching_issues" in phases
        assert "fetching_children" in phases


class TestImportWithChildFetching:
    """Tests for import_from_jira with child fetching."""

    def test_import_fetches_children(self) -> None:
        """Import from JQL fetches children of matched issues."""
        mock_client = MagicMock()

        epic_dict = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {
                "summary": "Epic",
                "description": "Test",
                "issuetype": {"id": "10000", "name": "Epic"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": None,
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        story_dict = {
            "id": "10002",
            "key": "STORY-1",
            "fields": {
                "summary": "Story under epic",
                "description": "Test",
                "issuetype": {"id": "10001", "name": "Story"},
                "status": {"id": "1", "name": "Open"},
                "assignee": None,
                "parent": {"id": "10001", "key": "EPIC-1"},
                "issuelinks": [],
                "resolutiondate": None,
                "worklog": None,
                "timetracking": None,
            },
        }

        mock_client.search.side_effect = [
            iter([epic_dict]),  # Initial query returns only epic
            iter([story_dict]),  # Children query returns story
            iter([]),  # No more children
        ]

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime.now().astimezone(),
            ),
        )

        result = import_from_jira(
            client=mock_client,
            jql='key = "EPIC-1"',  # Only matches epic, but children should be fetched
            config=config,
            project_name="Test Project",
        )

        # Both epic and story should be imported
        assert len(result.project.dag.node_map) == 2

        # Verify hierarchy
        tasks = {}
        for _node_id, persistent_id in result.project.dag.node_map.items():
            if persistent_id in result.project.persistent_tasks:
                ptask = result.project.persistent_tasks[persistent_id]
                task = ptask.versions[result.project.dag.current_version_id]
                if task.jira_reference is not None:
                    tasks[str(task.jira_reference.issue_key)] = task

        assert "EPIC-1" in tasks
        assert "STORY-1" in tasks
        assert tasks["EPIC-1"].parent_id is None
        assert tasks["STORY-1"].parent_id is not None
