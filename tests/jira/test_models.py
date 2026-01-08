"""Tests for fluxx.jira.models module."""

import pytest
from pydantic import ValidationError

from fluxx.jira.models import (
    JiraIssueKey,
    JiraReference,
)


class TestProjectKey:
    """Tests for ProjectKey validation."""

    def test_valid_project_key_simple(self) -> None:
        """Test valid simple project key."""
        key = JiraIssueKey(project_key="TEST", issue_number=123)
        assert key.project_key == "TEST"

    def test_valid_project_key_with_numbers(self) -> None:
        """Test valid project key with numbers."""
        key = JiraIssueKey(project_key="FHIR2", issue_number=123)
        assert key.project_key == "FHIR2"

    def test_valid_project_key_with_underscore(self) -> None:
        """Test valid project key with underscore."""
        key = JiraIssueKey(project_key="MY_PROJECT", issue_number=123)
        assert key.project_key == "MY_PROJECT"

    def test_invalid_project_key_lowercase(self) -> None:
        """Test that lowercase project keys are rejected."""
        with pytest.raises(ValidationError, match="project_key"):
            JiraIssueKey(project_key="test", issue_number=123)

    def test_invalid_project_key_starts_with_number(self) -> None:
        """Test that project keys starting with numbers are rejected."""
        with pytest.raises(ValidationError, match="project_key"):
            JiraIssueKey(project_key="1TEST", issue_number=123)

    def test_invalid_project_key_single_char(self) -> None:
        """Test that single character project keys are rejected."""
        with pytest.raises(ValidationError, match="project_key"):
            JiraIssueKey(project_key="T", issue_number=123)

    def test_invalid_project_key_empty(self) -> None:
        """Test that empty project keys are rejected."""
        with pytest.raises(ValidationError, match="project_key"):
            JiraIssueKey(project_key="", issue_number=123)


class TestJiraIssueKey:
    """Tests for JiraIssueKey model."""

    def test_from_string_valid(self) -> None:
        """Test parsing valid issue key string."""
        key = JiraIssueKey.from_string("FHIR-1234")
        assert key.project_key == "FHIR"
        assert key.issue_number == 1234

    def test_from_string_with_underscore(self) -> None:
        """Test parsing issue key with underscore in project."""
        key = JiraIssueKey.from_string("MY_PROJECT-999")
        assert key.project_key == "MY_PROJECT"
        assert key.issue_number == 999

    def test_from_string_invalid_format_no_dash(self) -> None:
        """Test that keys without dash are rejected."""
        with pytest.raises(ValueError, match="Invalid Jira issue key format"):
            JiraIssueKey.from_string("FHIR1234")

    def test_from_string_invalid_format_no_number(self) -> None:
        """Test that keys without number are rejected."""
        with pytest.raises(ValueError, match="Invalid Jira issue key format"):
            JiraIssueKey.from_string("FHIR-")

    def test_from_string_invalid_format_non_numeric(self) -> None:
        """Test that keys with non-numeric issue number are rejected."""
        with pytest.raises(ValueError, match="Invalid Jira issue key format"):
            JiraIssueKey.from_string("FHIR-ABC")

    def test_from_string_invalid_project_key(self) -> None:
        """Test that invalid project keys are rejected."""
        with pytest.raises(ValidationError):
            JiraIssueKey.from_string("fhir-123")

    def test_to_string(self) -> None:
        """Test string representation."""
        key = JiraIssueKey(project_key="FHIR", issue_number=1234)
        assert str(key) == "FHIR-1234"

    def test_issue_number_positive(self) -> None:
        """Test that issue number must be positive."""
        with pytest.raises(ValidationError, match="issue_number"):
            JiraIssueKey(project_key="TEST", issue_number=0)

    def test_issue_number_negative(self) -> None:
        """Test that negative issue numbers are rejected."""
        with pytest.raises(ValidationError, match="issue_number"):
            JiraIssueKey(project_key="TEST", issue_number=-1)

    def test_equality(self) -> None:
        """Test equality comparison."""
        key1 = JiraIssueKey(project_key="FHIR", issue_number=123)
        key2 = JiraIssueKey(project_key="FHIR", issue_number=123)
        key3 = JiraIssueKey(project_key="FHIR", issue_number=456)
        assert key1 == key2
        assert key1 != key3

    def test_hashable(self) -> None:
        """Test that JiraIssueKey is hashable (can be used in sets/dicts)."""
        key1 = JiraIssueKey(project_key="FHIR", issue_number=123)
        key2 = JiraIssueKey(project_key="FHIR", issue_number=123)
        key_set = {key1, key2}
        assert len(key_set) == 1

    def test_serialization(self) -> None:
        """Test JSON serialization."""
        key = JiraIssueKey(project_key="FHIR", issue_number=1234)
        data = key.model_dump()
        assert data == {"project_key": "FHIR", "issue_number": 1234}

    def test_deserialization(self) -> None:
        """Test JSON deserialization."""
        data = {"project_key": "FHIR", "issue_number": 1234}
        key = JiraIssueKey.model_validate(data)
        assert key.project_key == "FHIR"
        assert key.issue_number == 1234


class TestJiraReference:
    """Tests for JiraReference model."""

    def test_create_reference(self) -> None:
        """Test creating a Jira reference."""
        issue_key = JiraIssueKey(project_key="FHIR", issue_number=1234)
        ref = JiraReference(
            server_url="https://jira.example.com/jira",
            issue_key=issue_key,
        )
        assert ref.server_url == "https://jira.example.com/jira"
        assert ref.issue_key.project_key == "FHIR"
        assert ref.issue_key.issue_number == 1234

    def test_equality_same_server_and_key(self) -> None:
        """Test that references with same server and key are equal."""
        ref1 = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        ref2 = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        assert ref1 == ref2

    def test_inequality_different_server(self) -> None:
        """Test that references with different servers are not equal."""
        ref1 = JiraReference(
            server_url="https://jira1.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        ref2 = JiraReference(
            server_url="https://jira2.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        assert ref1 != ref2

    def test_inequality_different_key(self) -> None:
        """Test that references with different keys are not equal."""
        ref1 = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        ref2 = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=456),
        )
        assert ref1 != ref2

    def test_serialization(self) -> None:
        """Test JSON serialization."""
        ref = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=1234),
        )
        data = ref.model_dump()
        assert data == {
            "server_url": "https://jira.example.com",
            "issue_key": {"project_key": "FHIR", "issue_number": 1234},
        }

    def test_deserialization(self) -> None:
        """Test JSON deserialization."""
        data = {
            "server_url": "https://jira.example.com",
            "issue_key": {"project_key": "FHIR", "issue_number": 1234},
        }
        ref = JiraReference.model_validate(data)
        assert ref.server_url == "https://jira.example.com"
        assert ref.issue_key.project_key == "FHIR"
        assert ref.issue_key.issue_number == 1234

    def test_hashable(self) -> None:
        """Test that JiraReference is hashable."""
        ref1 = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        ref2 = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
        )
        ref_set = {ref1, ref2}
        assert len(ref_set) == 1


class TestJiraDurationHistoryEntry:
    """Tests for JiraDurationHistoryEntry model."""

    def test_create_history_entry(self) -> None:
        """Test creating a history entry."""
        from fluxx.jira.models import JiraDurationHistoryEntry

        entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
            original_estimate_seconds=28800,
            worker_jira_id="user123",
            issue_type="Story",
            total_logged_time_seconds=14400,
        )
        assert entry.server_url == "https://jira.example.com"
        assert entry.issue_key.project_key == "FHIR"
        assert entry.original_estimate_seconds == 28800
        assert entry.worker_jira_id == "user123"
        assert entry.issue_type == "Story"
        assert entry.total_logged_time_seconds == 14400

    def test_history_entry_optional_fields(self) -> None:
        """Test that some fields are optional."""
        from fluxx.jira.models import JiraDurationHistoryEntry

        entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="TEST", issue_number=1),
            issue_type="Bug",
        )
        assert entry.original_estimate_seconds is None
        assert entry.worker_jira_id is None
        assert entry.total_logged_time_seconds is None

    def test_history_entry_deduplication_key(self) -> None:
        """Test that (server_url, issue_key) forms identity for deduplication."""
        from fluxx.jira.models import JiraDurationHistoryEntry

        # Same server and key = same entry
        entry1 = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
            issue_type="Story",
            original_estimate_seconds=3600,
        )
        entry2 = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
            issue_type="Story",
            original_estimate_seconds=7200,  # Different value
        )
        # They represent the same issue even with different estimate values
        assert entry1.server_url == entry2.server_url
        assert entry1.issue_key == entry2.issue_key

    def test_history_entry_serialization(self) -> None:
        """Test JSON serialization."""
        from fluxx.jira.models import JiraDurationHistoryEntry

        entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
            issue_type="Task",
            original_estimate_seconds=3600,
        )
        data = entry.model_dump()
        assert data["server_url"] == "https://jira.example.com"
        assert data["issue_key"]["project_key"] == "FHIR"
        assert data["issue_type"] == "Task"

    def test_created_datetime_requires_timezone(self) -> None:
        """Test that created_datetime rejects naive datetime."""
        from datetime import UTC, datetime

        import pytest

        from fluxx.jira.models import JiraDurationHistoryEntry

        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(
            ValueError, match="created_datetime must have timezone info"
        ):
            JiraDurationHistoryEntry(
                server_url="https://jira.example.com",
                issue_key=JiraIssueKey(project_key="TEST", issue_number=1),
                issue_type="Bug",
                created_datetime=naive_dt,
            )

    def test_resolved_datetime_requires_timezone(self) -> None:
        """Test that resolved_datetime rejects naive datetime."""
        from datetime import UTC, datetime

        import pytest

        from fluxx.jira.models import JiraDurationHistoryEntry

        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(
            ValueError, match="resolved_datetime must have timezone info"
        ):
            JiraDurationHistoryEntry(
                server_url="https://jira.example.com",
                issue_key=JiraIssueKey(project_key="TEST", issue_number=1),
                issue_type="Bug",
                resolved_datetime=naive_dt,
            )

    def test_datetimes_accept_timezone_aware(self) -> None:
        """Test that datetime fields accept timezone-aware datetimes."""
        from datetime import UTC, datetime

        from fluxx.jira.models import JiraDurationHistoryEntry

        entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="TEST", issue_number=1),
            issue_type="Bug",
            created_datetime=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            resolved_datetime=datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
        )
        assert entry.created_datetime is not None
        assert entry.created_datetime.tzinfo is not None
        assert entry.resolved_datetime is not None
        assert entry.resolved_datetime.tzinfo is not None


class TestJiraSyncMetadata:
    """Tests for JiraSyncMetadata model."""

    def test_create_sync_metadata(self) -> None:
        """Test creating sync metadata."""
        from datetime import UTC, datetime

        from fluxx.jira.models import JiraDurationHistoryEntry, JiraSyncMetadata

        last_sync = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=123),
            issue_type="Story",
        )
        metadata = JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=last_sync,
            history_entries=[entry],
        )
        assert metadata.server_url == "https://jira.example.com"
        assert metadata.last_history_sync == last_sync
        assert len(metadata.history_entries) == 1

    def test_sync_metadata_empty_entries(self) -> None:
        """Test sync metadata with no history entries."""
        from datetime import UTC, datetime

        from fluxx.jira.models import JiraSyncMetadata

        metadata = JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2024, 1, 1, tzinfo=UTC),
            history_entries=[],
        )
        assert len(metadata.history_entries) == 0

    def test_sync_metadata_serialization(self) -> None:
        """Test JSON serialization."""
        from datetime import UTC, datetime

        from fluxx.jira.models import JiraSyncMetadata

        metadata = JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
            history_entries=[],
        )
        data = metadata.model_dump(mode="json")
        assert data["server_url"] == "https://jira.example.com"
        assert "last_history_sync" in data
        assert data["history_entries"] == []


class TestJiraConfig:
    """Tests for JiraConfig model."""

    def test_create_jira_config(self) -> None:
        """Test creating Jira config."""
        from datetime import UTC, datetime

        from fluxx.jira.models import JiraConfig, JiraSyncMetadata

        sync_metadata = JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2024, 1, 1, tzinfo=UTC),
            history_entries=[],
        )
        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=sync_metadata,
        )
        assert config.server_url == "https://jira.example.com"
        assert config.sync_metadata is not None

    def test_jira_config_serialization(self) -> None:
        """Test JSON serialization."""
        from datetime import UTC, datetime

        from fluxx.jira.models import JiraConfig, JiraSyncMetadata

        config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=datetime(2024, 1, 1, tzinfo=UTC),
                history_entries=[],
            ),
        )
        data = config.model_dump(mode="json")
        assert data["server_url"] == "https://jira.example.com"
        assert "sync_metadata" in data
