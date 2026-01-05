"""Pydantic models for Jira API responses.

These models validate external API input and provide type safety throughout
the data pipeline. Using `extra="ignore"` allows tolerance of fields we
don't need while ensuring the fields we depend on are present and valid.
"""

from pydantic import BaseModel, ConfigDict, Field


class JiraUser(BaseModel):
    """Represents a Jira user."""

    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(alias="accountId")
    display_name: str = Field(alias="displayName")
    active: bool = True


class JiraIssueType(BaseModel):
    """Represents a Jira issue type."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    subtask: bool = False


class JiraStatus(BaseModel):
    """Represents a Jira status."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class JiraTimeTracking(BaseModel):
    """Represents Jira time tracking fields."""

    model_config = ConfigDict(extra="ignore")

    original_estimate: str | None = Field(default=None, alias="originalEstimate")
    remaining_estimate: str | None = Field(default=None, alias="remainingEstimate")
    time_spent: str | None = Field(default=None, alias="timeSpent")
    original_estimate_seconds: int | None = Field(
        default=None, alias="originalEstimateSeconds"
    )
    remaining_estimate_seconds: int | None = Field(
        default=None, alias="remainingEstimateSeconds"
    )
    time_spent_seconds: int | None = Field(default=None, alias="timeSpentSeconds")


class JiraParentRef(BaseModel):
    """Reference to a parent issue."""

    model_config = ConfigDict(extra="ignore")

    id: str
    key: str


class JiraIssueLinkType(BaseModel):
    """Represents an issue link type."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str
    inward: str | None = None
    outward: str | None = None


class JiraLinkedIssue(BaseModel):
    """Brief representation of a linked issue."""

    model_config = ConfigDict(extra="ignore")

    id: str
    key: str


class JiraIssueLink(BaseModel):
    """Represents a link between issues."""

    model_config = ConfigDict(extra="ignore")

    id: str
    link_type: JiraIssueLinkType = Field(alias="type")
    inward_issue: JiraLinkedIssue | None = Field(default=None, alias="inwardIssue")
    outward_issue: JiraLinkedIssue | None = Field(default=None, alias="outwardIssue")


class JiraWorklogEntry(BaseModel):
    """Represents a single worklog entry."""

    model_config = ConfigDict(extra="ignore")

    id: str
    author: JiraUser
    comment: str | None = None
    started: str
    time_spent: str = Field(alias="timeSpent")
    time_spent_seconds: int = Field(alias="timeSpentSeconds")


class JiraWorklog(BaseModel):
    """Represents a worklog container with entries."""

    model_config = ConfigDict(extra="ignore")

    start_at: int = Field(alias="startAt")
    max_results: int = Field(alias="maxResults")
    total: int
    worklogs: list[JiraWorklogEntry]


class JiraIssueFields(BaseModel):
    """Represents the fields object of a Jira issue."""

    model_config = ConfigDict(extra="ignore")

    summary: str
    description: str | None = None
    issuetype: JiraIssueType
    status: JiraStatus
    assignee: JiraUser | None = None
    timetracking: JiraTimeTracking | None = None
    parent: JiraParentRef | None = None
    issuelinks: list[JiraIssueLink] | None = None
    worklog: JiraWorklog | None = None

    # Custom fields - story points (customfield_10473 is common but configurable)
    story_points: float | None = Field(default=None, alias="customfield_10473")

    # Timestamps
    created: str | None = None
    updated: str | None = None
    resolutiondate: str | None = None


class JiraIssueResponse(BaseModel):
    """Top-level response model for a Jira issue.

    This model validates the structure of issue responses from the
    Jira REST API, ensuring we get the fields we need while ignoring
    extra fields that may be present.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    key: str
    fields: JiraIssueFields
