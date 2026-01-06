"""Tests for Jira sync dialog."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.gui.jira.sync_dialog import JiraSyncDialog
from fluxx.jira.models import JiraConfig, JiraReference, JiraSyncMetadata


@pytest.fixture
def project_without_jira_tasks() -> Project:
    """Create a project without any Jira-linked tasks."""
    task = Task(
        id=TaskId("t1"),
        title="Local Task",
        description="Not from Jira",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        jira_reference=None,
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=[Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)],
        jira_config=None,
    )


@pytest.fixture
def project_with_jira_tasks() -> Project:
    """Create a project with Jira-linked tasks."""
    from fluxx.jira.models import JiraIssueKey

    task = Task(
        id=TaskId("t1"),
        title="Jira Task",
        description="From Jira",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        jira_reference=JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="TEST", issue_number=1),
        ),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    jira_config = JiraConfig(
        server_url="https://jira.example.com",
        sync_metadata=JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2024, 1, 1, tzinfo=UTC),
            history_entries=[],
        ),
    )

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=[Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)],
        jira_config=jira_config,
    )


def test_dialog_initialization(
    qtbot: QtBot, project_without_jira_tasks: Project
) -> None:
    """Test dialog initializes with expected widgets."""
    with patch.object(JiraSyncDialog, "_start_sync"):
        dialog = JiraSyncDialog(project_without_jira_tasks)
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Update from Jira"
        assert dialog.isModal()
        assert hasattr(dialog, "info_label")
        assert hasattr(dialog, "progress_bar")
        assert hasattr(dialog, "progress_label")


def test_dialog_shows_no_tasks_message(
    qtbot: QtBot, project_without_jira_tasks: Project
) -> None:
    """Test dialog shows message when no Jira-linked tasks."""
    dialog = JiraSyncDialog(project_without_jira_tasks)
    qtbot.addWidget(dialog)

    assert "No Jira-linked tasks" in dialog.info_label.text()
    assert dialog.progress_label.isHidden()
    assert dialog.progress_bar.isHidden()


def test_dialog_shows_task_count(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog shows count of tasks to sync."""
    mock_result = MagicMock()
    mock_result.project = project_with_jira_tasks
    mock_result.updated_count = 0
    mock_result.created_count = 0
    mock_result.deleted_keys = []
    mock_result.warnings = []

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch("fluxx.gui.jira.sync_dialog.sync_from_jira", return_value=mock_result),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        # Should complete and show success
        assert "Sync complete" in dialog.info_label.text()


def test_dialog_handles_token_not_found(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog handles TokenNotFoundError."""
    from pathlib import Path

    from fluxx.jira.auth import TokenNotFoundError

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch(
            "fluxx.gui.jira.sync_dialog.read_token",
            side_effect=TokenNotFoundError(Path("/fake/path")),
        ),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        assert not dialog.status_label.isHidden()
        assert "token not found" in dialog.status_label.text().lower()


def test_dialog_handles_sync_exception(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog handles sync exceptions."""
    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch(
            "fluxx.gui.jira.sync_dialog.sync_from_jira",
            side_effect=Exception("Connection error"),
        ),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        assert not dialog.status_label.isHidden()
        assert "Sync failed" in dialog.status_label.text()
        assert "Connection error" in dialog.status_label.text()


def test_dialog_emits_sync_completed(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog emits sync_completed signal."""
    mock_result = MagicMock()
    mock_result.project = project_with_jira_tasks
    mock_result.updated_count = 1
    mock_result.created_count = 0
    mock_result.deleted_keys = []
    mock_result.warnings = []

    signal_received: list[object] = []

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch("fluxx.gui.jira.sync_dialog.sync_from_jira", return_value=mock_result),
        patch.object(JiraSyncDialog, "_start_sync"),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        dialog.sync_completed.connect(lambda r: signal_received.append(r))
        qtbot.addWidget(dialog)

    # Now run sync with patches still active
    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch("fluxx.gui.jira.sync_dialog.sync_from_jira", return_value=mock_result),
    ):
        # Call the real _start_sync method
        JiraSyncDialog._start_sync(dialog)

    assert len(signal_received) == 1
    assert signal_received[0] is mock_result


def test_dialog_shows_success_summary(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog shows success summary with counts."""
    mock_result = MagicMock()
    mock_result.project = project_with_jira_tasks
    mock_result.updated_count = 2
    mock_result.created_count = 1
    mock_result.deleted_keys = ["TEST-3"]
    mock_result.warnings = []

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch("fluxx.gui.jira.sync_dialog.sync_from_jira", return_value=mock_result),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        assert "2 updated" in dialog.info_label.text()
        assert "1 created" in dialog.info_label.text()
        assert "1 removed" in dialog.info_label.text()


def test_dialog_shows_no_changes(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog shows 'No changes' when nothing synced."""
    mock_result = MagicMock()
    mock_result.project = project_with_jira_tasks
    mock_result.updated_count = 0
    mock_result.created_count = 0
    mock_result.deleted_keys = []
    mock_result.warnings = []

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch("fluxx.gui.jira.sync_dialog.sync_from_jira", return_value=mock_result),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        assert "No changes" in dialog.info_label.text()


def test_dialog_progress_callback(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test dialog updates progress during sync."""
    mock_result = MagicMock()
    mock_result.project = project_with_jira_tasks
    mock_result.updated_count = 0
    mock_result.created_count = 0
    mock_result.deleted_keys = []
    mock_result.warnings = []

    progress_callback_captured = None

    def capture_callback(*args: object, **kwargs: object) -> MagicMock:
        nonlocal progress_callback_captured
        progress_callback_captured = kwargs.get("progress_callback")
        return mock_result

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch(
            "fluxx.gui.jira.sync_dialog.sync_from_jira", side_effect=capture_callback
        ),
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        # Verify progress callback was passed
        assert progress_callback_captured is not None


def test_show_close_button(qtbot: QtBot, project_without_jira_tasks: Project) -> None:
    """Test _show_close_button replaces Cancel with Close."""
    dialog = JiraSyncDialog(project_without_jira_tasks)
    qtbot.addWidget(dialog)

    # After showing no tasks, Close button should be present
    from PySide6.QtWidgets import QDialogButtonBox

    close_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Close)
    assert close_button is not None


def test_run_sync_uses_config_timezone(
    qtbot: QtBot, project_with_jira_tasks: Project
) -> None:
    """Test _run_sync uses timezone from config."""
    # Modify project to have a specific timezone
    assert project_with_jira_tasks.jira_config is not None
    project_with_jira_tasks.jira_config.server_timezone = "America/New_York"

    mock_result = MagicMock()
    mock_result.project = project_with_jira_tasks
    mock_result.updated_count = 0
    mock_result.created_count = 0
    mock_result.deleted_keys = []
    mock_result.warnings = []

    with (
        patch("fluxx.gui.jira.sync_dialog.get_token_path"),
        patch("fluxx.gui.jira.sync_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.sync_dialog.JiraClient"),
        patch(
            "fluxx.gui.jira.sync_dialog.sync_from_jira", return_value=mock_result
        ) as mock_sync,
    ):
        dialog = JiraSyncDialog(project_with_jira_tasks)
        qtbot.addWidget(dialog)

        # Verify config was passed with correct timezone
        call_kwargs = mock_sync.call_args[1]
        assert call_kwargs["config"].server_timezone == "America/New_York"
