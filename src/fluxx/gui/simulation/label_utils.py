"""Utility functions for formatting labels in visualization widgets."""

MAX_LABEL_LENGTH = 20
ELLIPSIS = "…"


def truncate_task_label(
    title: str,
    jira_issue_key: str | None = None,
    max_length: int = MAX_LABEL_LENGTH,
) -> tuple[str, str]:
    """Truncate a task title to fit within the specified character limit.

    If a Jira issue key is provided, it is prepended to the title.
    If the combined string exceeds max_length, it is truncated and ends with "…".

    Args:
        title: The task title
        jira_issue_key: Optional Jira issue key (e.g., "CORE-123")
        max_length: Maximum length of the resulting label (default 20)

    Returns:
        Tuple of (truncated_label, full_label) where:
        - truncated_label: The label truncated to max_length with "…" if needed
        - full_label: The complete label without truncation (for tooltips)

    Examples:
        >>> truncate_task_label("Short title")
        ('Short title', 'Short title')

        >>> truncate_task_label("My really long title for a ticket", "CORE-123")
        ('CORE-123 My really …', 'CORE-123 My really long title for a ticket')

        >>> truncate_task_label("My really long title for a ticket")
        ('My really long titl…', 'My really long title for a ticket')
    """
    # Build full label
    full_label = f"{jira_issue_key} {title}" if jira_issue_key else title

    # If it fits, return as-is
    if len(full_label) <= max_length:
        return full_label, full_label

    # Truncate with ellipsis
    # We need room for the ellipsis character, so truncate at max_length - 1
    truncated_label = full_label[: max_length - 1] + ELLIPSIS
    return truncated_label, full_label
