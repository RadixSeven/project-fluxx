"""Tests for Jira task linker."""

from unittest.mock import MagicMock

import pytest

from fluxx.data.models import Task, TaskId, Triangular
from fluxx.jira.client import JiraClientError
from fluxx.jira.linker import (
    IssueNotFoundError,
    LinkResult,
    NoServerConfiguredError,
    TaskLinker,
)
from fluxx.jira.models import JiraIssueKey


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock JiraClient."""
    client = MagicMock()
    client.server_url = "https://jira.example.com"
    return client


@pytest.fixture
def existing_task() -> Task:
    """Create an existing task without Jira reference."""
    return Task(
        id=TaskId("task-1"),
        title="My Task",
        description="Task description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )


@pytest.fixture
def jira_issue_response() -> dict[str, object]:
    """Sample Jira issue response."""
    return {
        "id": "12345",
        "key": "FHIR-1234",
        "fields": {
            "summary": "Fix the login bug",
            "description": "Users cannot login with special characters",
            "issuetype": {"id": "1", "name": "Bug", "subtask": False},
            "status": {"id": "10000", "name": "To Do"},
            "assignee": None,
            "timetracking": {
                "originalEstimateSeconds": 14400,
                "remainingEstimateSeconds": 14400,
            },
            "parent": None,
            "issuelinks": [],
        },
    }


def test_link_task_to_jira_valid_key(
    mock_client: MagicMock, existing_task: Task, jira_issue_response: dict[str, object]
) -> None:
    """Test linking a task to a valid Jira issue."""
    mock_client.get_issue.return_value = jira_issue_response

    linker = TaskLinker(mock_client)
    result = linker.link("FHIR-1234", existing_task)

    assert isinstance(result, LinkResult)
    assert result.task.jira_reference is not None
    assert result.task.jira_reference.issue_key == JiraIssueKey(
        project_key="FHIR", issue_number=1234
    )
    assert result.task.jira_reference.server_url == "https://jira.example.com"
    assert result.summary == "Fix the login bug"
    assert result.issue_type == "Bug"

    # Verify client was called correctly
    mock_client.get_issue.assert_called_once()
    call_kwargs = mock_client.get_issue.call_args.kwargs
    assert call_kwargs["key"] == "FHIR-1234"


def test_link_task_preserves_original_fields(
    mock_client: MagicMock, existing_task: Task, jira_issue_response: dict[str, object]
) -> None:
    """Test that linking preserves the original task fields."""
    mock_client.get_issue.return_value = jira_issue_response

    linker = TaskLinker(mock_client)
    result = linker.link("FHIR-1234", existing_task)

    # Original fields should be preserved
    assert result.task.id == existing_task.id
    assert result.task.title == existing_task.title
    assert result.task.description == existing_task.description
    assert result.task.duration_distribution == existing_task.duration_distribution


def test_link_task_sets_jira_issue_type(
    mock_client: MagicMock, existing_task: Task, jira_issue_response: dict[str, object]
) -> None:
    """Test that linking sets the jira_issue_type field."""
    mock_client.get_issue.return_value = jira_issue_response

    linker = TaskLinker(mock_client)
    result = linker.link("FHIR-1234", existing_task)

    assert result.task.jira_issue_type == "Bug"


def test_link_task_to_jira_invalid_key(mock_client: MagicMock) -> None:
    """Test linking with an invalid issue key format."""
    linker = TaskLinker(mock_client)
    task = Task(
        id=TaskId("task-1"),
        title="My Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    with pytest.raises(ValueError, match="Invalid Jira issue key format"):
        linker.link("invalid-key", task)

    # Client should not be called for invalid key
    mock_client.get_issue.assert_not_called()


def test_link_task_to_jira_issue_not_found(
    mock_client: MagicMock, existing_task: Task
) -> None:
    """Test linking when issue doesn't exist in Jira."""
    mock_client.get_issue.side_effect = JiraClientError("HTTP 404: Issue not found")

    linker = TaskLinker(mock_client)

    with pytest.raises(IssueNotFoundError) as exc_info:
        linker.link("FHIR-9999", existing_task)

    assert "FHIR-9999" in str(exc_info.value)


def test_link_task_no_server_configured(existing_task: Task) -> None:
    """Test linking when no client is configured."""
    linker = TaskLinker(client=None)

    with pytest.raises(NoServerConfiguredError):
        linker.link("FHIR-1234", existing_task)


def test_link_result_fields(
    mock_client: MagicMock, existing_task: Task, jira_issue_response: dict[str, object]
) -> None:
    """Test that LinkResult contains all expected fields."""
    mock_client.get_issue.return_value = jira_issue_response

    linker = TaskLinker(mock_client)
    result = linker.link("FHIR-1234", existing_task)

    # Verify all result fields
    assert result.task is not None
    assert result.summary == "Fix the login bug"
    assert result.issue_type == "Bug"
    assert result.issue_key == "FHIR-1234"
    assert result.server_url == "https://jira.example.com"


def test_link_task_with_description(
    mock_client: MagicMock, existing_task: Task
) -> None:
    """Test that result includes issue description."""
    response = {
        "id": "12345",
        "key": "TEST-100",
        "fields": {
            "summary": "Test Issue",
            "description": "This is a detailed description",
            "issuetype": {"id": "2", "name": "Story", "subtask": False},
            "status": {"id": "10000", "name": "Open"},
        },
    }
    mock_client.get_issue.return_value = response

    linker = TaskLinker(mock_client)
    result = linker.link("TEST-100", existing_task)

    assert result.description == "This is a detailed description"


def test_link_task_with_none_description(
    mock_client: MagicMock, existing_task: Task
) -> None:
    """Test handling of null description."""
    response = {
        "id": "12345",
        "key": "TEST-100",
        "fields": {
            "summary": "Test Issue",
            "description": None,
            "issuetype": {"id": "2", "name": "Story", "subtask": False},
            "status": {"id": "10000", "name": "Open"},
        },
    }
    mock_client.get_issue.return_value = response

    linker = TaskLinker(mock_client)
    result = linker.link("TEST-100", existing_task)

    assert result.description is None


def test_link_task_case_insensitive_key(
    mock_client: MagicMock, existing_task: Task, jira_issue_response: dict[str, object]
) -> None:
    """Test that issue key is normalized to uppercase."""
    mock_client.get_issue.return_value = jira_issue_response

    linker = TaskLinker(mock_client)
    result = linker.link("fhir-1234", existing_task)

    assert result.task.jira_reference is not None
    assert result.task.jira_reference.issue_key.project_key == "FHIR"

    # Client should be called with uppercase key
    mock_client.get_issue.assert_called_once()
    call_kwargs = mock_client.get_issue.call_args.kwargs
    assert call_kwargs["key"] == "FHIR-1234"
