"""Tests for Jira import dialog."""

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
from fluxx.gui.jira.import_dialog import JiraImportDialog
from fluxx.jira.models import JiraConfig, JiraSyncMetadata


@pytest.fixture
def project_without_jira() -> Project:
    """Create a project without Jira configuration."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
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

    workers = [
        Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0),
    ]

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=workers,
        jira_config=None,
    )


@pytest.fixture
def project_with_jira() -> Project:
    """Create a project with Jira configuration."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
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

    workers = [
        Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0),
    ]

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
        workers=workers,
        jira_config=jira_config,
    )


def test_dialog_shows_server_input_when_not_configured(
    qtbot: QtBot, project_without_jira: Project
) -> None:
    """Test that server URL input is shown when Jira is not configured."""
    dialog = JiraImportDialog(project_without_jira)
    qtbot.addWidget(dialog)

    # Server URL input should not be hidden (widget is shown when dialog displays)
    assert not dialog.server_url_input.isHidden()
    assert not dialog.server_url_label.isHidden()


def test_dialog_hides_server_input_when_configured(
    qtbot: QtBot, project_with_jira: Project
) -> None:
    """Test that server URL input is hidden when Jira is configured."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # Server URL input should be hidden
    assert dialog.server_url_input.isHidden()
    assert dialog.server_url_label.isHidden()

    # Should show configured server info
    assert "jira.example.com" in dialog.server_info_label.text()


def test_dialog_has_jql_input(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test that dialog has JQL query input."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # JQL input should not be hidden (widget is shown when dialog displays)
    assert not dialog.jql_input.isHidden()
    # Should have placeholder text
    assert dialog.jql_input.placeholderText() != ""


def test_dialog_validates_server_url(
    qtbot: QtBot, project_without_jira: Project
) -> None:
    """Test that dialog validates server URL format."""
    dialog = JiraImportDialog(project_without_jira)
    qtbot.addWidget(dialog)

    # Set invalid URL
    dialog.server_url_input.setText("not-a-url")
    dialog.jql_input.setText("project = FHIR")

    # Import button should be disabled with invalid URL
    assert not dialog.import_button.isEnabled()

    # Set valid URL
    dialog.server_url_input.setText("https://jira.example.com")

    # Import button should now be enabled
    assert dialog.import_button.isEnabled()


def test_dialog_validates_jql_required(
    qtbot: QtBot, project_with_jira: Project
) -> None:
    """Test that dialog requires JQL query."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # Clear JQL input
    dialog.jql_input.setText("")

    # Import button should be disabled
    assert not dialog.import_button.isEnabled()

    # Set JQL
    dialog.jql_input.setText("project = FHIR")

    # Import button should be enabled
    assert dialog.import_button.isEnabled()


def test_dialog_shows_progress(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test that progress widgets are initially hidden."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # Progress widgets should be hidden initially
    assert dialog.progress_label.isHidden()
    assert dialog.progress_bar.isHidden()


def test_dialog_reject_closes(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test that Cancel button closes dialog."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # Click Cancel button
    cancel_button = dialog.button_box.button(dialog.button_box.StandardButton.Cancel)
    assert cancel_button is not None

    with qtbot.waitSignal(dialog.rejected):
        cancel_button.click()


def test_dialog_import_emits_result(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test that successful import emits result signal."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.jql_input.setText("project = FHIR")

    # Mock the import function
    mock_result = MagicMock()
    mock_result.project = project_with_jira
    mock_result.warnings = []

    with (
        patch.object(dialog, "_run_import", return_value=mock_result),
        qtbot.waitSignal(dialog.import_completed, timeout=5000),
    ):
        dialog._on_import()


def test_dialog_disables_inputs_during_import(
    qtbot: QtBot, project_with_jira: Project
) -> None:
    """Test that inputs are disabled during import."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # Disable inputs
    dialog._set_inputs_enabled(False)

    assert not dialog.jql_input.isEnabled()
    assert not dialog.import_button.isEnabled()

    # Re-enable
    dialog._set_inputs_enabled(True)

    assert dialog.jql_input.isEnabled()


def test_dialog_project_name_defaults_to_jql(
    qtbot: QtBot, project_with_jira: Project
) -> None:
    """Test that project name defaults based on JQL."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    # Set JQL with project
    dialog.jql_input.setText("project = FHIR")

    # Project name should default to project key
    assert (
        dialog.project_name_input.text() == ""
        or "FHIR" in dialog.project_name_input.text()
    )


def test_dialog_initialization(qtbot: QtBot, project_without_jira: Project) -> None:
    """Test dialog initializes with expected widgets."""
    dialog = JiraImportDialog(project_without_jira)
    qtbot.addWidget(dialog)

    # Check window properties
    assert dialog.windowTitle() == "Import from Jira"
    assert dialog.isModal()

    # Check essential widgets exist
    assert hasattr(dialog, "server_url_input")
    assert hasattr(dialog, "jql_input")
    assert hasattr(dialog, "project_name_input")
    assert hasattr(dialog, "progress_bar")
    assert hasattr(dialog, "import_button")


def test_get_server_url_from_config(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test _get_server_url returns URL from config."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    url = dialog._get_server_url()
    assert url == "https://jira.example.com"


def test_get_server_url_from_input(qtbot: QtBot, project_without_jira: Project) -> None:
    """Test _get_server_url returns URL from input when no config."""
    dialog = JiraImportDialog(project_without_jira)
    qtbot.addWidget(dialog)

    dialog.server_url_input.setText("https://custom.jira.com")
    url = dialog._get_server_url()
    assert url == "https://custom.jira.com"


def test_get_project_name_custom(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test _get_project_name returns custom name when provided."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.project_name_input.setText("My Custom Project")
    dialog.jql_input.setText("project = FHIR")

    name = dialog._get_project_name()
    assert name == "My Custom Project"


def test_get_project_name_from_jql(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test _get_project_name extracts from JQL when no custom name."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.project_name_input.setText("")
    dialog.jql_input.setText("project = FHIR AND status = Open")

    name = dialog._get_project_name()
    assert name == "Jira Import - FHIR"


def test_get_project_name_default(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test _get_project_name returns default when no JQL project match."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.project_name_input.setText("")
    dialog.jql_input.setText("status = Open")  # No project= clause

    name = dialog._get_project_name()
    assert name == "Jira Import"


def test_on_import_validation_fails_early_return(
    qtbot: QtBot, project_without_jira: Project
) -> None:
    """Test _on_import returns early when validation fails."""
    dialog = JiraImportDialog(project_without_jira)
    qtbot.addWidget(dialog)

    # Invalid URL and empty JQL
    dialog.server_url_input.setText("")
    dialog.jql_input.setText("")

    # Should return early - no exception, no signal
    dialog._on_import()

    # Progress should still be hidden
    assert dialog.progress_label.isHidden()
    assert dialog.progress_bar.isHidden()


def test_on_import_token_not_found_error(
    qtbot: QtBot, project_with_jira: Project
) -> None:
    """Test _on_import handles TokenNotFoundError."""
    from pathlib import Path

    from fluxx.jira.auth import TokenNotFoundError

    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.jql_input.setText("project = FHIR")

    # Mock _run_import to raise TokenNotFoundError
    with patch.object(
        dialog,
        "_run_import",
        side_effect=TokenNotFoundError(Path("/fake/token/path")),
    ):
        dialog._on_import()

    # Should show error message
    assert not dialog.status_label.isHidden()
    assert "token not found" in dialog.status_label.text().lower()

    # Progress should be hidden
    assert dialog.progress_label.isHidden()
    assert dialog.progress_bar.isHidden()

    # Inputs should be re-enabled
    assert dialog.jql_input.isEnabled()


def test_on_import_general_exception(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test _on_import handles general exceptions."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.jql_input.setText("project = FHIR")

    # Mock _run_import to raise a general exception
    with patch.object(
        dialog,
        "_run_import",
        side_effect=Exception("Connection timeout"),
    ):
        dialog._on_import()

    # Should show error message
    assert not dialog.status_label.isHidden()
    assert "Import failed" in dialog.status_label.text()
    assert "Connection timeout" in dialog.status_label.text()

    # Progress should be hidden
    assert dialog.progress_label.isHidden()

    # Inputs should be re-enabled
    assert dialog.jql_input.isEnabled()


def test_run_import_calls_import_from_jira(
    qtbot: QtBot, project_with_jira: Project
) -> None:
    """Test _run_import calls import_from_jira with correct arguments."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.jql_input.setText("project = TEST")
    dialog.project_name_input.setText("Test Project")

    # Mock all the dependencies
    mock_result = MagicMock()
    mock_result.project = project_with_jira
    mock_result.warnings = []

    with (
        patch("fluxx.gui.jira.import_dialog.get_token_path") as mock_get_token_path,
        patch("fluxx.gui.jira.import_dialog.read_token") as mock_read_token,
        patch("fluxx.gui.jira.import_dialog.JiraClient") as mock_client_class,
        patch(
            "fluxx.gui.jira.import_dialog.import_from_jira", return_value=mock_result
        ) as mock_import,
    ):
        from pathlib import Path

        mock_get_token_path.return_value = Path("/fake/token/path")
        mock_read_token.return_value = "fake-token"
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        result = dialog._run_import()

        # Verify token was read
        mock_get_token_path.assert_called_once_with("https://jira.example.com")
        mock_read_token.assert_called_once()

        # Verify client was created
        mock_client_class.assert_called_once_with(
            server_url="https://jira.example.com",
            token="fake-token",
        )

        # Verify import was called
        mock_import.assert_called_once()
        call_kwargs = mock_import.call_args[1]
        assert call_kwargs["jql"] == "project = TEST"
        assert call_kwargs["project_name"] == "Test Project"
        assert call_kwargs["client"] == mock_client

        # Verify result
        assert result == mock_result


def test_run_import_uses_server_timezone_from_config(qtbot: QtBot) -> None:
    """Test _run_import uses server timezone from existing config."""
    # Create a project with a specific timezone
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
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
        server_timezone="America/New_York",  # Specific timezone
        sync_metadata=JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=datetime(2024, 1, 1, tzinfo=UTC),
            history_entries=[],
        ),
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=[],
        jira_config=jira_config,
    )

    dialog = JiraImportDialog(project)
    qtbot.addWidget(dialog)

    dialog.jql_input.setText("project = TEST")

    mock_result = MagicMock()

    with (
        patch("fluxx.gui.jira.import_dialog.get_token_path"),
        patch("fluxx.gui.jira.import_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.import_dialog.JiraClient"),
        patch(
            "fluxx.gui.jira.import_dialog.import_from_jira", return_value=mock_result
        ) as mock_import,
    ):
        dialog._run_import()

        # Check config has correct timezone
        call_kwargs = mock_import.call_args[1]
        config = call_kwargs["config"]
        assert config.server_timezone == "America/New_York"


def test_run_import_progress_callback(qtbot: QtBot, project_with_jira: Project) -> None:
    """Test _run_import registers progress callback."""
    dialog = JiraImportDialog(project_with_jira)
    qtbot.addWidget(dialog)

    dialog.jql_input.setText("project = TEST")

    mock_result = MagicMock()

    with (
        patch("fluxx.gui.jira.import_dialog.get_token_path"),
        patch("fluxx.gui.jira.import_dialog.read_token", return_value="token"),
        patch("fluxx.gui.jira.import_dialog.JiraClient"),
        patch(
            "fluxx.gui.jira.import_dialog.import_from_jira", return_value=mock_result
        ) as mock_import,
    ):
        dialog._run_import()

        # Verify progress_callback was passed
        call_kwargs = mock_import.call_args[1]
        assert "progress_callback" in call_kwargs
        assert call_kwargs["progress_callback"] is not None

        # Call the progress callback to verify it updates the UI
        from fluxx.jira.importer import ImportProgress

        progress = ImportProgress(
            total_issues=10,
            processed_issues=5,
            current_phase="fetching_issues",
        )
        call_kwargs["progress_callback"](progress)

        # Progress bar should be updated
        assert dialog.progress_bar.value() == 50
        assert "fetching_issues" in dialog.progress_label.text()
