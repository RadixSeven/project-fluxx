"""Tests for Jira API response types."""

from fluxx.jira.api_types import JiraIssueResponse
from tests.jira.conftest import load_fixture


class TestJiraIssueResponseBasic:
    """Tests for basic JiraIssueResponse parsing."""

    def test_parse_issue_basic_fields(self) -> None:
        """Test parsing basic issue fields."""
        raw = load_fixture("issue_basic.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.key == "FHIR-1234"
        assert issue.id == "12345"
        assert issue.fields.summary == "Implement OAuth2 authentication"
        assert issue.fields.description == "Add OAuth2 support for API authentication"

    def test_parse_issue_issuetype(self) -> None:
        """Test parsing issue type."""
        raw = load_fixture("issue_basic.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.issuetype.name == "Story"
        assert issue.fields.issuetype.id == "10001"
        assert issue.fields.issuetype.subtask is False

    def test_parse_issue_status(self) -> None:
        """Test parsing status."""
        raw = load_fixture("issue_basic.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.status.name == "Done"
        assert issue.fields.status.id == "10000"

    def test_parse_issue_assignee(self) -> None:
        """Test parsing assignee."""
        raw = load_fixture("issue_basic.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.assignee is not None
        assert issue.fields.assignee.account_id == "abc123"
        assert issue.fields.assignee.display_name == "Alice Smith"

    def test_parse_issue_timetracking(self) -> None:
        """Test parsing time tracking."""
        raw = load_fixture("issue_basic.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.timetracking is not None
        assert issue.fields.timetracking.original_estimate_seconds == 28800
        assert issue.fields.timetracking.remaining_estimate_seconds == 0
        assert issue.fields.timetracking.time_spent_seconds == 36000

    def test_parse_issue_story_points(self) -> None:
        """Test parsing story points custom field."""
        raw = load_fixture("issue_basic.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.story_points == 5.0


class TestJiraIssueResponseParent:
    """Tests for parsing issues with parent."""

    def test_parse_issue_with_parent(self) -> None:
        """Test parsing issue with parent reference."""
        raw = load_fixture("issue_with_parent.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.key == "FHIR-1235"
        assert issue.fields.parent is not None
        assert issue.fields.parent.key == "FHIR-1000"
        assert issue.fields.parent.id == "12345"

    def test_parse_subtask_issuetype(self) -> None:
        """Test parsing subtask issue type."""
        raw = load_fixture("issue_with_parent.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.issuetype.name == "Sub-task"
        assert issue.fields.issuetype.subtask is True


class TestJiraIssueResponseLinks:
    """Tests for parsing issue links."""

    def test_parse_issue_links_dependencies(self) -> None:
        """Test parsing issue dependencies."""
        raw = load_fixture("issue_with_links.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.issuelinks is not None
        depends_on = [
            link
            for link in issue.fields.issuelinks
            if link.link_type.name == "Depends" and link.outward_issue is not None
        ]
        assert len(depends_on) == 2

    def test_parse_issue_links_outward(self) -> None:
        """Test parsing outward issue links."""
        raw = load_fixture("issue_with_links.json")
        issue = JiraIssueResponse.model_validate(raw)

        outward_links = [
            link for link in issue.fields.issuelinks or [] if link.outward_issue
        ]
        assert len(outward_links) == 2
        assert outward_links[0].outward_issue is not None
        assert outward_links[0].outward_issue.key == "FHIR-1234"

    def test_parse_issue_links_inward(self) -> None:
        """Test parsing inward issue links."""
        raw = load_fixture("issue_with_links.json")
        issue = JiraIssueResponse.model_validate(raw)

        inward_links = [
            link for link in issue.fields.issuelinks or [] if link.inward_issue
        ]
        assert len(inward_links) == 1
        assert inward_links[0].inward_issue is not None
        assert inward_links[0].inward_issue.key == "FHIR-1238"


class TestJiraIssueResponseWorklogs:
    """Tests for parsing worklogs."""

    def test_parse_issue_worklogs(self) -> None:
        """Test parsing worklogs."""
        raw = load_fixture("issue_with_worklogs.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.worklog is not None
        assert len(issue.fields.worklog.worklogs) == 3

    def test_parse_worklog_details(self) -> None:
        """Test parsing worklog details."""
        raw = load_fixture("issue_with_worklogs.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.worklog is not None
        worklog = issue.fields.worklog.worklogs[0]
        assert worklog.author.account_id == "abc123"
        assert worklog.time_spent_seconds == 28800
        assert worklog.comment == "Initial implementation"

    def test_parse_worklog_total(self) -> None:
        """Test parsing worklog total."""
        raw = load_fixture("issue_with_worklogs.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.worklog is not None
        assert issue.fields.worklog.total == 3


class TestJiraIssueResponseMinimal:
    """Tests for parsing minimal issues."""

    def test_parse_issue_handles_missing_optional_fields(self) -> None:
        """Test that optional fields default correctly."""
        raw = load_fixture("issue_minimal.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.key == "TEST-1"
        assert issue.fields.summary == "Minimal issue"
        assert issue.fields.story_points is None
        assert issue.fields.timetracking is None
        assert issue.fields.assignee is None
        assert issue.fields.parent is None
        assert issue.fields.worklog is None
        assert issue.fields.issuelinks is None

    def test_parse_issue_minimal_issuetype(self) -> None:
        """Test parsing minimal issue type."""
        raw = load_fixture("issue_minimal.json")
        issue = JiraIssueResponse.model_validate(raw)

        assert issue.fields.issuetype.name == "Task"


class TestJiraIssueResponseExtraFields:
    """Tests for handling extra fields in API responses."""

    def test_extra_fields_are_ignored(self) -> None:
        """Test that extra unknown fields are ignored."""
        raw = {
            "id": "1",
            "key": "TEST-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "unknown_field": "should be ignored",
            "fields": {
                "summary": "Test",
                "issuetype": {"name": "Task", "id": "1"},
                "status": {"name": "Done", "id": "1"},
                "another_unknown": "also ignored",
            },
        }
        # Should not raise
        issue = JiraIssueResponse.model_validate(raw)
        assert issue.key == "TEST-1"
