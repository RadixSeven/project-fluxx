"""Tests for the label_utils module."""

from fluxx.gui.simulation.label_utils import (
    ELLIPSIS,
    MAX_LABEL_LENGTH,
    truncate_task_label,
)


class TestTruncateTaskLabel:
    """Tests for truncate_task_label function."""

    def test_short_title_without_jira_key(self) -> None:
        """Short titles without Jira key should not be truncated."""
        truncated, full = truncate_task_label("Short title")
        assert truncated == "Short title"
        assert full == "Short title"

    def test_short_title_with_jira_key(self) -> None:
        """Short titles with Jira key should include the key prefix."""
        truncated, full = truncate_task_label("Task", "CORE-1")
        assert truncated == "CORE-1 Task"
        assert full == "CORE-1 Task"

    def test_exact_max_length_title(self) -> None:
        """Titles exactly at max length should not be truncated."""
        # Create a title that's exactly 20 characters
        title = "a" * 20
        truncated, full = truncate_task_label(title)
        assert len(truncated) == 20
        assert truncated == title
        assert full == title

    def test_long_title_without_jira_key_is_truncated(self) -> None:
        """Long titles without Jira key should be truncated with ellipsis."""
        long_title = "My really long title for a ticket"
        truncated, full = truncate_task_label(long_title)

        # Should be truncated to MAX_LABEL_LENGTH
        assert len(truncated) == MAX_LABEL_LENGTH
        assert truncated.endswith(ELLIPSIS)
        assert truncated == "My really long titl…"
        assert full == long_title

    def test_long_title_with_jira_key_is_truncated(self) -> None:
        """Long titles with Jira key should include key and be truncated."""
        long_title = "My really long title for a ticket"
        truncated, full = truncate_task_label(long_title, "CORE-123")

        # Should be truncated to MAX_LABEL_LENGTH
        assert len(truncated) == MAX_LABEL_LENGTH
        assert truncated.endswith(ELLIPSIS)
        assert truncated == "CORE-123 My really …"
        assert full == "CORE-123 My really long title for a ticket"

    def test_custom_max_length(self) -> None:
        """Custom max_length parameter should be respected."""
        title = "A moderately long title"
        truncated, full = truncate_task_label(title, max_length=10)

        assert len(truncated) == 10
        assert truncated.endswith(ELLIPSIS)
        assert truncated == "A moderat…"
        assert full == title

    def test_empty_title(self) -> None:
        """Empty titles should work correctly."""
        truncated, full = truncate_task_label("")
        assert truncated == ""
        assert full == ""

    def test_empty_title_with_jira_key(self) -> None:
        """Empty title with Jira key should show just the key."""
        truncated, full = truncate_task_label("", "ABC-1")
        assert truncated == "ABC-1 "
        assert full == "ABC-1 "

    def test_unicode_title(self) -> None:
        """Unicode characters in titles should be handled correctly."""
        title = "日本語タイトルが長すぎます"
        truncated, full = truncate_task_label(title)

        # Length is measured in characters, not bytes
        assert len(truncated) <= MAX_LABEL_LENGTH
        assert full == title

    def test_full_label_always_preserved(self) -> None:
        """Full label should always be the complete untruncated version."""
        cases = [
            ("Short", None),
            ("Very long title that exceeds the limit", None),
            ("Short", "KEY-1"),
            ("Very long title that exceeds the limit", "KEY-1"),
        ]
        for title, jira_key in cases:
            truncated, full = truncate_task_label(title, jira_key)
            expected_full = f"{jira_key} {title}" if jira_key else title
            assert full == expected_full

    def test_truncation_preserves_ellipsis_space(self) -> None:
        """Truncation should leave room for the ellipsis character."""
        title = "x" * 30  # 30 characters
        truncated, _ = truncate_task_label(title)

        # Should be 19 chars + ellipsis = 20
        assert len(truncated) == MAX_LABEL_LENGTH
        assert truncated[-1] == ELLIPSIS
        assert truncated[:-1] == "x" * 19
