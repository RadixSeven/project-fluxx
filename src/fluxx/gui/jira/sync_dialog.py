"""Dialog for syncing project with Jira."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from fluxx.data.models import Project
from fluxx.jira.auth import TokenNotFoundError, get_token_path, read_token
from fluxx.jira.client import JiraClient
from fluxx.jira.importer import (
    ImportProgress,
    SyncResult,
    collect_jira_referenced_tasks,
    sync_from_jira,
)
from fluxx.jira.models import JiraConfig, JiraSyncMetadata


class JiraSyncDialog(QDialog):
    """Dialog for syncing project with Jira.

    Syncs all Jira-linked tasks in the project with their current
    state in Jira. Shows progress and reports results.

    Signals:
        sync_completed: Emitted when sync finishes successfully,
            with SyncResult as parameter
    """

    sync_completed: Signal = Signal(object)

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Initialize the sync dialog.

        Args:
            project: The project to sync
            parent: Parent widget
        """
        super().__init__(parent)
        self.project = project

        self.setWindowTitle("Update from Jira")
        self.setModal(True)
        self.resize(400, 200)

        self._create_widgets()
        self._create_layout()
        self._connect_signals()

        # Start sync automatically
        self._start_sync()

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        # Info label
        self.info_label = QLabel("Syncing project with Jira...")

        # Progress widgets
        self.progress_label = QLabel("Collecting tasks...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)

        # Status label for errors
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: red;")
        self.status_label.hide()

        # Buttons (Cancel only during sync, OK after completion)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)

    def _create_layout(self) -> None:
        """Create dialog layout."""
        layout = QVBoxLayout()

        layout.addWidget(self.info_label)
        layout.addSpacing(10)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.button_box.rejected.connect(self.reject)

    def _start_sync(self) -> None:
        """Start the sync process."""
        # Check if there are any Jira-linked tasks
        tasks_by_server = collect_jira_referenced_tasks(self.project)

        if not tasks_by_server:
            self.info_label.setText("No Jira-linked tasks found in project.")
            self.progress_label.hide()
            self.progress_bar.hide()
            self._show_close_button()
            return

        # Get unique servers
        servers = list(tasks_by_server.keys())
        self.info_label.setText(
            f"Syncing {sum(len(t) for t in tasks_by_server.values())} tasks "
            f"from {len(servers)} server(s)..."
        )

        try:
            result = self._run_sync(servers)
            self.sync_completed.emit(result)
            self._show_success(result)
        except TokenNotFoundError as e:
            self.status_label.setText(
                f"Jira token not found. Run 'fluxx-jira-auth' first.\n{e}"
            )
            self.status_label.show()
            self.progress_label.hide()
            self.progress_bar.hide()
            self._show_close_button()
        except Exception as e:
            self.status_label.setText(f"Sync failed: {e}")
            self.status_label.show()
            self.progress_label.hide()
            self.progress_bar.hide()
            self._show_close_button()

    def _run_sync(self, servers: list[str]) -> SyncResult:
        """Run sync for all servers.

        Args:
            servers: List of server URLs to sync

        Returns:
            Combined SyncResult from all servers
        """
        # For now, we sync with the first server only
        # In the future, we might need to handle multiple servers
        server_url = servers[0]

        # Read token
        token_path = get_token_path(server_url)
        token = read_token(token_path)

        # Create client
        client = JiraClient(server_url=server_url, token=token)

        # Build config
        server_timezone = "UTC"
        if self.project.jira_config:
            server_timezone = self.project.jira_config.server_timezone

        # Build sync metadata from existing config or defaults
        if self.project.jira_config:
            sync_metadata = self.project.jira_config.sync_metadata
        else:
            from datetime import UTC, datetime

            sync_metadata = JiraSyncMetadata(
                server_url=server_url,
                last_history_sync=datetime.now(UTC),
                history_entries=[],
            )

        config = JiraConfig(
            server_url=server_url,
            server_timezone=server_timezone,
            sync_metadata=sync_metadata,
        )

        # Sync
        def progress_callback(progress: ImportProgress) -> None:
            if progress.total_issues > 0:
                pct = int(progress.processed_issues / progress.total_issues * 100)
                self.progress_bar.setValue(pct)
            self.progress_label.setText(f"{progress.current_phase}...")

        return sync_from_jira(
            project=self.project,
            client=client,
            config=config,
            progress_callback=progress_callback,
        )

    def _show_success(self, result: SyncResult) -> None:
        """Show success message after sync.

        Args:
            result: The sync result
        """
        summary_parts = []
        if result.updated_count > 0:
            summary_parts.append(f"{result.updated_count} updated")
        if result.created_count > 0:
            summary_parts.append(f"{result.created_count} created")
        if result.deleted_keys:
            summary_parts.append(f"{len(result.deleted_keys)} removed")

        summary = ", ".join(summary_parts) if summary_parts else "No changes"

        self.info_label.setText(f"Sync complete: {summary}")
        self.progress_label.hide()
        self.progress_bar.hide()
        self._show_close_button()

    def _show_close_button(self) -> None:
        """Replace Cancel button with Close button."""
        self.button_box.clear()
        self.button_box.addButton(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.accept)
