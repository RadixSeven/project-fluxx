"""Dialog for importing projects from Jira."""

import re
from datetime import UTC, datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import Project
from fluxx.jira.auth import TokenNotFoundError, get_token_path, read_token
from fluxx.jira.client import JiraClient
from fluxx.jira.importer import ImportProgress, ImportResult, import_from_jira
from fluxx.jira.models import JiraConfig, JiraSyncMetadata

# URL validation pattern
URL_PATTERN = re.compile(
    r"^https?://[a-zA-Z0-9][-a-zA-Z0-9.]*[a-zA-Z0-9](:\d+)?(/.*)?$"
)


class JiraImportDialog(QDialog):
    """Dialog for importing issues from Jira.

    Allows user to specify:
    - Server URL (if not configured)
    - JQL query to select issues
    - Project name for the imported project

    Shows progress during import and emits result when complete.

    Signals:
        import_completed: Emitted when import finishes successfully,
            with ImportResult as parameter
    """

    import_completed: Signal = Signal(object)

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Initialize the import dialog.

        Args:
            project: The current project (may have existing Jira config)
            parent: Parent widget
        """
        super().__init__(parent)
        self.project = project

        self.setWindowTitle("Import from Jira")
        self.setModal(True)
        self.resize(500, 300)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._update_import_button()

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        has_jira_config = self.project.jira_config is not None

        # Server URL (shown if not configured)
        self.server_url_label = QLabel("Server URL:")
        self.server_url_input = QLineEdit()
        self.server_url_input.setPlaceholderText("https://jira.example.com")

        # Server info label (shown if configured)
        self.server_info_label = QLabel()
        if has_jira_config and self.project.jira_config is not None:
            server_url = self.project.jira_config.server_url
            # Extract hostname for display
            hostname = server_url.replace("https://", "").replace("http://", "")
            self.server_info_label.setText(f"Connected to: {hostname}")
        else:
            self.server_info_label.setText("")

        # Show/hide based on configuration
        self.server_url_label.setVisible(not has_jira_config)
        self.server_url_input.setVisible(not has_jira_config)
        self.server_info_label.setVisible(has_jira_config)

        # JQL query
        self.jql_label = QLabel("JQL Query:")
        self.jql_input = QLineEdit()
        self.jql_input.setPlaceholderText("project = PROJ AND type = Epic")

        # Project name
        self.project_name_label = QLabel("Project Name:")
        self.project_name_input = QLineEdit()
        self.project_name_input.setPlaceholderText("(Optional - defaults from JQL)")

        # Progress widgets (initially hidden)
        self.progress_label = QLabel("Importing...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_label.hide()
        self.progress_bar.hide()

        # Status label for errors/warnings
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: red;")
        self.status_label.hide()

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.import_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert self.import_button is not None
        self.import_button.setText("Import")

    def _create_layout(self) -> None:
        """Create dialog layout."""
        layout = QVBoxLayout()

        # Form for input fields
        form = QFormLayout()

        # Server URL or info
        if not self.project.jira_config:
            form.addRow(self.server_url_label, self.server_url_input)
        else:
            form.addRow("", self.server_info_label)

        form.addRow(self.jql_label, self.jql_input)
        form.addRow(self.project_name_label, self.project_name_input)

        layout.addLayout(form)
        layout.addSpacing(10)

        # Status label
        layout.addWidget(self.status_label)

        # Progress widgets
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addStretch()

        # Buttons
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.button_box.accepted.connect(self._on_import)
        self.button_box.rejected.connect(self.reject)

        # Update button state when inputs change
        self.jql_input.textChanged.connect(self._update_import_button)
        self.server_url_input.textChanged.connect(self._update_import_button)

    def _update_import_button(self) -> None:
        """Update import button enabled state based on validation."""
        is_valid = self._validate_inputs()
        self.import_button.setEnabled(is_valid)

    def _validate_inputs(self) -> bool:
        """Validate all inputs.

        Returns:
            True if all inputs are valid
        """
        # Check JQL is not empty
        if not self.jql_input.text().strip():
            return False

        # Check server URL if not configured
        if not self.project.jira_config:
            url = self.server_url_input.text().strip()
            if not url or not URL_PATTERN.match(url):
                return False

        return True

    def _get_server_url(self) -> str:
        """Get the server URL to use.

        Returns:
            Server URL from config or input
        """
        if self.project.jira_config:
            return self.project.jira_config.server_url
        return self.server_url_input.text().strip()

    def _get_project_name(self) -> str:
        """Get the project name to use.

        Returns:
            Project name from input or derived from JQL
        """
        name = self.project_name_input.text().strip()
        if name:
            return name

        # Try to extract project key from JQL
        jql = self.jql_input.text()
        match = re.search(r"project\s*=\s*(\w+)", jql, re.IGNORECASE)
        if match:
            return f"Jira Import - {match.group(1)}"

        return "Jira Import"

    def _on_import(self) -> None:
        """Handle Import button click."""
        if not self._validate_inputs():
            return

        # Hide status, show progress
        self.status_label.hide()
        self.progress_label.show()
        self.progress_bar.show()
        self.progress_bar.setValue(0)

        # Disable inputs
        self._set_inputs_enabled(False)

        try:
            result = self._run_import()
            self.import_completed.emit(result)
            self.accept()
        except TokenNotFoundError:
            self.status_label.setText(
                "Jira token not found. Please run 'fluxx-jira-auth' first."
            )
            self.status_label.show()
            self._set_inputs_enabled(True)
            self.progress_label.hide()
            self.progress_bar.hide()
        except Exception as e:
            self.status_label.setText(f"Import failed: {e}")
            self.status_label.show()
            self._set_inputs_enabled(True)
            self.progress_label.hide()
            self.progress_bar.hide()

    def _run_import(self) -> ImportResult:
        """Run the actual import.

        Returns:
            ImportResult with imported project and warnings
        """
        server_url = self._get_server_url()
        jql = self.jql_input.text().strip()
        project_name = self._get_project_name()

        # Read token
        token_path = get_token_path(server_url)
        token = read_token(token_path)

        # Create client
        client = JiraClient(server_url=server_url, token=token)

        # Build config
        server_timezone = "UTC"
        if self.project.jira_config:
            server_timezone = self.project.jira_config.server_timezone

        config = JiraConfig(
            server_url=server_url,
            server_timezone=server_timezone,
            sync_metadata=JiraSyncMetadata(
                server_url=server_url,
                last_history_sync=datetime.now(UTC),
                history_entries=[],
            ),
        )

        # Import
        def progress_callback(progress: ImportProgress) -> None:
            if progress.total_issues > 0:
                pct = int(progress.processed_issues / progress.total_issues * 100)
                self.progress_bar.setValue(pct)
            self.progress_label.setText(f"{progress.current_phase}...")

        return import_from_jira(
            client=client,
            jql=jql,
            config=config,
            project_name=project_name,
            progress_callback=progress_callback,
        )

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Enable or disable input widgets.

        Args:
            enabled: Whether to enable inputs
        """
        self.server_url_input.setEnabled(enabled)
        self.jql_input.setEnabled(enabled)
        self.project_name_input.setEnabled(enabled)
        self.import_button.setEnabled(enabled and self._validate_inputs())
