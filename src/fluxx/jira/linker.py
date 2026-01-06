"""Task linker for connecting Fluxx tasks to Jira issues.

This module provides functionality to link existing Fluxx tasks to Jira issues
by fetching issue metadata and updating the task's jira_reference field.
"""

from dataclasses import dataclass

from fluxx.data.models import Task
from fluxx.jira.api_types import JiraIssueResponse
from fluxx.jira.client import JiraClient, JiraClientError
from fluxx.jira.models import JiraIssueKey, JiraReference


class IssueNotFoundError(Exception):
    """Raised when a Jira issue cannot be found."""

    def __init__(self, issue_key: str, message: str | None = None) -> None:
        """Initialize the error.

        Args:
            issue_key: The issue key that was not found
            message: Optional additional message
        """
        self.issue_key = issue_key
        msg = f"Jira issue '{issue_key}' not found"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(msg)


class NoServerConfiguredError(Exception):
    """Raised when attempting to link without a configured Jira server."""

    def __init__(self) -> None:
        super().__init__(
            "No Jira server configured. Please configure a Jira server first."
        )


@dataclass
class LinkResult:
    """Result of linking a task to a Jira issue.

    Attributes:
        task: The task with updated jira_reference
        summary: The issue summary from Jira
        description: The issue description from Jira (may be None)
        issue_type: The Jira issue type (e.g., 'Bug', 'Story')
        issue_key: The Jira issue key (e.g., 'FHIR-1234')
        server_url: The Jira server URL
    """

    task: Task
    summary: str
    description: str | None
    issue_type: str
    issue_key: str
    server_url: str


class TaskLinker:
    """Links Fluxx tasks to Jira issues.

    This class fetches issue metadata from Jira and creates a JiraReference
    to link an existing Fluxx task to its corresponding Jira issue.
    """

    # Fields to fetch from Jira when linking
    LINK_FIELDS = [
        "summary",
        "description",
        "issuetype",
        "status",
    ]

    def __init__(self, client: JiraClient | None) -> None:
        """Initialize the linker.

        Args:
            client: JiraClient instance, or None if no server configured
        """
        self._client = client

    def link(self, issue_key_str: str, task: Task) -> LinkResult:
        """Link a task to a Jira issue.

        Fetches the issue from Jira and updates the task's jira_reference
        to point to that issue.

        Args:
            issue_key_str: Jira issue key (e.g., 'FHIR-1234')
            task: The task to link

        Returns:
            LinkResult containing the updated task and issue metadata

        Raises:
            NoServerConfiguredError: If no client is configured
            ValueError: If the issue key format is invalid
            IssueNotFoundError: If the issue doesn't exist in Jira
        """
        if self._client is None:
            raise NoServerConfiguredError()

        # Normalize and validate issue key
        normalized_key = issue_key_str.upper()
        issue_key = JiraIssueKey.from_string(normalized_key)

        # Fetch issue from Jira
        try:
            raw_response = self._client.get_issue(
                key=str(issue_key),
                fields=self.LINK_FIELDS,
            )
        except JiraClientError as e:
            raise IssueNotFoundError(str(issue_key), str(e)) from e

        # Parse response
        issue = JiraIssueResponse.model_validate(raw_response)

        # Create reference
        jira_reference = JiraReference(
            server_url=self._client.server_url,
            issue_key=issue_key,
        )

        # Create updated task (Task is frozen, so we create a new instance)
        updated_task = task.model_copy(
            update={
                "jira_reference": jira_reference,
                "jira_issue_type": issue.fields.issuetype.name,
            }
        )

        return LinkResult(
            task=updated_task,
            summary=issue.fields.summary,
            description=issue.fields.description,
            issue_type=issue.fields.issuetype.name,
            issue_key=str(issue_key),
            server_url=self._client.server_url,
        )
