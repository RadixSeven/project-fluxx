"""Jira-related data models for Project Fluxx.

This module defines the Pydantic models used to represent Jira entities
within Fluxx, including issue keys, references, and sync metadata.

Note: JiraDurationDistribution is defined in fluxx.data.models (alongside
other DurationDistribution subclasses) to avoid circular imports.
Import it from fluxx.data.models directly.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class EstimateSource(str, Enum):
    """Source of the estimate for a history entry.

    This tracks how the original_estimate_seconds value was derived,
    enabling future filtering/analysis of estimate accuracy by source.
    """

    FROM_ORIGINAL_ESTIMATE = "from original estimate field"
    FROM_SUMMING_CHILDREN = "from summing children"


# Project key pattern: starts with uppercase letter, followed by uppercase letters,
# digits, or underscores. Minimum 2 characters.
PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")

# Type alias for project key (validated string)
ProjectKey = Annotated[str, Field(description="Jira project key (e.g., 'FHIR')")]


class JiraIssueKey(BaseModel, frozen=True):
    """Represents a Jira issue key (e.g., FHIR-1234).

    This is a frozen (immutable) model that can be used as a dictionary key
    or in sets.

    Attributes:
        project_key: The project key portion (e.g., 'FHIR')
        issue_number: The issue number portion (e.g., 1234)
    """

    project_key: ProjectKey = Field(description="Jira project key")
    issue_number: int = Field(gt=0, description="Issue number (positive integer)")

    @field_validator("project_key")
    @classmethod
    def validate_project_key(cls, v: str) -> str:
        """Validate that project_key matches Jira's format."""
        if not PROJECT_KEY_PATTERN.match(v):
            raise ValueError(
                f"Invalid project key '{v}': must match pattern [A-Z][A-Z0-9_]+ "
                "(start with uppercase letter, followed by uppercase letters, "
                "digits, or underscores, minimum 2 characters)"
            )
        return v

    @classmethod
    def from_string(cls, key_string: str) -> "JiraIssueKey":
        """Parse a Jira issue key from string format.

        Args:
            key_string: Issue key in format 'PROJECT-123'

        Returns:
            JiraIssueKey instance

        Raises:
            ValueError: If the string format is invalid
        """
        if "-" not in key_string:
            raise ValueError(
                f"Invalid Jira issue key format: '{key_string}'. "
                "Expected format: PROJECT-123"
            )

        project_key, issue_num_str = key_string.rsplit("-", 1)

        if not issue_num_str:
            raise ValueError(
                f"Invalid Jira issue key format: '{key_string}'. "
                "Missing issue number after dash"
            )

        try:
            issue_number = int(issue_num_str)
        except ValueError:
            raise ValueError(
                f"Invalid Jira issue key format: '{key_string}'. "
                f"Issue number '{issue_num_str}' is not a valid integer"
            ) from None

        return cls(project_key=project_key, issue_number=issue_number)

    def __str__(self) -> str:
        """Return the standard string representation (e.g., 'FHIR-1234')."""
        return f"{self.project_key}-{self.issue_number}"


class JiraReference(BaseModel, frozen=True):
    """Reference to a Jira issue on a specific server.

    This uniquely identifies a Jira issue across different Jira instances.
    Frozen (immutable) so it can be used as a dictionary key or in sets.

    Attributes:
        server_url: Base URL of the Jira server (e.g., 'https://jira.example.com')
        issue_key: The issue key on that server
    """

    server_url: str = Field(description="Jira server base URL")
    issue_key: JiraIssueKey = Field(description="Issue key on this server")


class JiraDurationHistoryEntry(BaseModel):
    """Historical data about a Jira issue for duration estimation.

    This captures the timing information from completed issues that can be
    used to build duration distributions for similar future work.

    Attributes:
        server_url: Base URL of the Jira server
        issue_key: The issue key this entry is for
        original_estimate_seconds: Original time estimate in seconds (if set)
        worker_jira_id: Jira user identifier (name for Data Center, accountId for Cloud)
        issue_type: Jira issue type (e.g., 'Story', 'Bug', 'Task')
        total_logged_time_seconds: Total time logged on the issue in seconds
        remaining_estimate_seconds: Remaining estimate in seconds at resolution
        story_points: Story points assigned to the issue
        created_datetime: When the issue was created
        resolved_datetime: When the issue was resolved
    """

    server_url: str = Field(description="Jira server base URL")
    issue_key: JiraIssueKey = Field(description="Issue key for this entry")
    original_estimate_seconds: int | None = Field(
        default=None, description="Original time estimate in seconds"
    )
    worker_jira_id: str | None = Field(
        default=None,
        description="Jira user identifier (name for Data Center, accountId for Cloud)",
    )
    issue_type: str = Field(description="Jira issue type (e.g., 'Story', 'Bug')")
    total_logged_time_seconds: int | None = Field(
        default=None, description="Total time logged in seconds"
    )
    # New fields for exploratory data analysis
    remaining_estimate_seconds: int | None = Field(
        default=None, description="Remaining estimate in seconds at resolution"
    )
    story_points: float | None = Field(
        default=None, description="Story points assigned to the issue"
    )
    created_datetime: datetime | None = Field(
        default=None, description="When the issue was created"
    )
    resolved_datetime: datetime | None = Field(
        default=None, description="When the issue was resolved"
    )
    estimate_source: EstimateSource = Field(description="How the estimate was derived")

    @field_validator("created_datetime")
    @classmethod
    def created_datetime_has_timezone(cls, d: datetime | None) -> datetime | None:
        """Validate that created_datetime has timezone info if present."""
        if d is not None and d.tzinfo is None:
            raise ValueError("created_datetime must have timezone info")
        return d

    @field_validator("resolved_datetime")
    @classmethod
    def resolved_datetime_has_timezone(cls, d: datetime | None) -> datetime | None:
        """Validate that resolved_datetime has timezone info if present."""
        if d is not None and d.tzinfo is None:
            raise ValueError("resolved_datetime must have timezone info")
        return d


class JiraSyncMetadata(BaseModel):
    """Metadata about synchronization with a Jira server.

    Tracks the state of historical data sync to enable incremental updates.

    Attributes:
        server_url: Base URL of the Jira server
        last_history_sync: Timestamp of the last successful history sync
        history_entries: List of historical issue entries from this server
    """

    server_url: str = Field(description="Jira server base URL")
    last_history_sync: datetime = Field(description="Last successful sync timestamp")
    history_entries: list[JiraDurationHistoryEntry] = Field(
        default_factory=list, description="Historical issue entries"
    )


class JiraConfig(BaseModel):
    """Configuration for a Jira server connection.

    Stores the server URL and associated sync metadata.

    Attributes:
        server_url: Base URL of the Jira server
        server_timezone: IANA timezone name for the server (e.g., 'America/New_York').
            Used as fallback when datetime strings lack timezone information.
        sync_metadata: Synchronization metadata for this server
    """

    server_url: str = Field(description="Jira server base URL")
    server_timezone: str = Field(
        default="UTC",
        description="IANA timezone name for fallback datetime parsing",
    )
    sync_metadata: JiraSyncMetadata = Field(description="Sync state for this server")
