"""Main window for Project Fluxx application."""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
)

from fluxx.data.models import Triangular
from fluxx.gui.controller import ProjectController
from fluxx.gui.panels import DAGPanel, EditorPanel


class MainWindow(QMainWindow):
    """Main application window for Project Fluxx.

    Layout:
    - Menu bar: File (New, Open, Save, Save As, Exit), Edit (Undo, Redo)
    - Two-panel layout with QSplitter:
      - Left panel (800px): DAGPanel (DAG view or list view)
      - Right panel (600px): EditorPanel (task/branch editors)
    - Window title shows filename and modified state
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Project Fluxx")
        self.setGeometry(100, 100, 1400, 800)

        # Create controller
        self.controller = ProjectController()

        # Create menu bar
        self._create_menu_bar()

        # Create two-panel layout
        self._create_panels()

        # Connect to controller signals
        self.controller.file_path_changed.connect(self._update_window_title)
        self.controller.modified_changed.connect(self._update_window_title)
        self.controller.project_changed.connect(self._update_undo_redo_actions)

        # Initialize window title
        self._update_window_title()
        self._update_undo_redo_actions()

    def _create_menu_bar(self) -> None:
        """Create menu bar with File and Edit menus."""
        menubar = self.menuBar()
        assert menubar is not None  # menuBar() always returns a menu bar

        # File menu
        file_menu = menubar.addMenu("&File")
        assert file_menu is not None  # addMenu() always returns a menu

        # New
        new_action = QAction("&New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._on_new)
        file_menu.addAction(new_action)

        # Open
        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        # Save
        self.save_action = QAction("&Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._on_save)
        file_menu.addAction(self.save_action)

        # Save As
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        assert edit_menu is not None  # addMenu() always returns a menu

        # Undo
        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(self.undo_action)

        # Redo
        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        # New Task
        new_task_action = QAction("New &Task", self)
        new_task_action.setShortcut("Ctrl+T")
        new_task_action.triggered.connect(self._on_new_task)
        edit_menu.addAction(new_task_action)

        # New Branch
        new_branch_action = QAction("New &Branch", self)
        new_branch_action.setShortcut("Ctrl+B")
        new_branch_action.triggered.connect(self._on_new_branch)
        edit_menu.addAction(new_branch_action)

    def _create_panels(self) -> None:
        """Create two-panel layout with splitter."""
        # Create panels
        self.dag_panel = DAGPanel(self.controller)
        self.editor_panel = EditorPanel(self.controller)

        # Create splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.dag_panel)
        splitter.addWidget(self.editor_panel)

        # Set initial sizes (800px left, 600px right)
        splitter.setSizes([800, 600])

        # Set as central widget
        self.setCentralWidget(splitter)

    def _update_window_title(self) -> None:
        """Update window title based on file path and modified state."""
        file_path = self.controller.get_file_path()
        is_modified = self.controller.is_modified()

        title = "Untitled" if file_path is None else file_path.name

        if is_modified:
            title += "*"

        title = f"Project Fluxx - {title}"
        self.setWindowTitle(title)

        # Update Save action enabled state
        self.save_action.setEnabled(is_modified and file_path is not None)

    def _update_undo_redo_actions(self) -> None:
        """Update undo/redo action enabled state."""
        self.undo_action.setEnabled(self.controller.can_undo())
        self.redo_action.setEnabled(self.controller.can_redo())

    def _check_unsaved_changes(self) -> bool:
        """Check for unsaved changes and prompt user.

        Returns:
            True if it's safe to continue (no changes or user chose to discard),
            False if operation should be cancelled
        """
        if not self.controller.is_modified():
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save them?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if reply == QMessageBox.StandardButton.Save:
            # Try to save
            self._on_save()
            # Check if save succeeded (modified flag should be cleared)
            return not self.controller.is_modified()
        # Return True for Discard, False for Cancel
        return reply == QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        """Handle window close event.

        Args:
            event: Close event
        """
        if event is None:
            return
        if self._check_unsaved_changes():
            event.accept()
        else:
            event.ignore()

    # File operations

    def _on_new(self) -> None:
        """Handle New menu action."""
        if not self._check_unsaved_changes():
            return
        self.controller.new_project("Untitled")

    def _on_open(self) -> None:
        """Handle Open menu action."""
        if not self._check_unsaved_changes():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "Project Fluxx Files (*.fluxx);;All Files (*)",
        )
        if file_path:
            try:
                self.controller.open_project(Path(file_path))
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Opening Project",
                    f"Failed to open project: {e}",
                )

    def _on_save(self) -> None:
        """Handle Save menu action."""
        if self.controller.get_file_path() is None:
            # No file path set, use Save As
            self._on_save_as()
        else:
            try:
                self.controller.save_project()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Saving Project",
                    f"Failed to save project: {e}",
                )

    def _on_save_as(self) -> None:
        """Handle Save As menu action."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            str(Path.home() / "Untitled.fluxx"),
            "Project Fluxx Files (*.fluxx);;All Files (*)",
        )
        if file_path:
            try:
                # Ensure .fluxx extension
                path = Path(file_path)
                if path.suffix != ".fluxx":
                    path = path.with_suffix(".fluxx")
                self.controller.save_project_as(path)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Saving Project",
                    f"Failed to save project: {e}",
                )

    # Edit operations

    def _on_undo(self) -> None:
        """Handle Undo menu action."""
        if self.controller.can_undo():
            try:
                self.controller.undo()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to undo: {e}",
                )

    def _on_redo(self) -> None:
        """Handle Redo menu action."""
        if self.controller.can_redo():
            try:
                self.controller.redo()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to redo: {e}",
                )

    def _on_new_task(self) -> None:
        """Handle New Task menu action."""
        # Prompt for task title
        title, ok = QInputDialog.getText(
            self, "New Task", "Enter task title:", text="New Task"
        )

        if ok and title:
            try:
                # Create task with default values
                task_id = self.controller.create_task(
                    title=title,
                    description="",
                    duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
                )

                # Select the new task
                from fluxx.data.models import NodeId

                self.controller.select_node(NodeId(task_id))
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to create task: {e}",
                )

    def _on_new_branch(self) -> None:
        """Handle New Branch menu action."""
        # Prompt for branch title
        title, ok = QInputDialog.getText(
            self, "New Branch", "Enter branch title:", text="New Branch"
        )

        if ok and title:
            try:
                # Create branch with default values
                branch_id = self.controller.create_branch(
                    title=title,
                    description="",
                    possible_worlds=[],
                )

                # Select the new branch
                from fluxx.data.models import NodeId

                self.controller.select_node(NodeId(branch_id))
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to create branch: {e}",
                )
