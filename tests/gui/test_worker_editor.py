"""Tests for WorkerEditor widget."""

from pytestqt.qtbot import QtBot

from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.worker_editor import WorkerEditor


def test_worker_editor_initialization(qtbot: QtBot) -> None:
    """Test WorkerEditor initialization."""
    controller = ProjectController()
    controller.new_project("Test Project")

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    assert editor.controller is controller
    assert editor.workers_table.rowCount() == 0


def test_worker_editor_loads_workers(qtbot: QtBot) -> None:
    """Test loading workers into the editor."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add workers
    controller.add_worker(name="Alice", hours_per_workday=8.0)
    controller.add_worker(name="Bob", hours_per_workday=7.5)

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Should display both workers
    assert editor.workers_table.rowCount() == 2

    # Check first worker
    item_0_0 = editor.workers_table.item(0, 0)
    item_0_2 = editor.workers_table.item(0, 2)
    assert item_0_0 is not None
    assert item_0_2 is not None
    assert item_0_0.text() == "Alice"
    assert item_0_2.text() == "8.0"

    # Check second worker
    item_1_0 = editor.workers_table.item(1, 0)
    item_1_2 = editor.workers_table.item(1, 2)
    assert item_1_0 is not None
    assert item_1_2 is not None
    assert item_1_0.text() == "Bob"
    assert item_1_2.text() == "7.5"


def test_worker_editor_add_worker(qtbot: QtBot) -> None:
    """Test adding a worker via the editor."""
    controller = ProjectController()
    controller.new_project("Test Project")

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Initially empty
    assert editor.workers_table.rowCount() == 0

    # Click add worker button
    editor.add_worker_button.click()

    # Should have one worker
    assert editor.workers_table.rowCount() == 1
    item_0 = editor.workers_table.item(0, 0)
    item_2 = editor.workers_table.item(0, 2)
    assert item_0 is not None
    assert item_2 is not None
    assert item_0.text() == "New Worker"
    assert item_2.text() == "8.0"


def test_worker_editor_remove_worker(qtbot: QtBot) -> None:
    """Test removing a worker via the editor."""
    controller = ProjectController()
    controller.new_project("Test Project")

    # Add workers
    controller.add_worker(name="Alice", hours_per_workday=8.0)
    controller.add_worker(name="Bob", hours_per_workday=7.5)

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    assert editor.workers_table.rowCount() == 2

    # Select first row
    editor.workers_table.setCurrentCell(0, 0)

    # Remove button should be enabled
    assert editor.remove_worker_button.isEnabled()

    # Click remove
    editor.remove_worker_button.click()

    # Should have one worker left
    assert editor.workers_table.rowCount() == 1
    item = editor.workers_table.item(0, 0)
    assert item is not None
    assert item.text() == "Bob"


def test_worker_editor_edit_worker_name(qtbot: QtBot) -> None:
    """Test editing a worker name."""
    controller = ProjectController()
    controller.new_project("Test Project")

    worker_id = controller.add_worker(name="Alice", hours_per_workday=8.0)

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Edit the name
    item = editor.workers_table.item(0, 0)
    assert item is not None
    item.setText("Alice Smith")

    # Check controller was updated
    workers = controller.get_workers()
    assert len(workers) == 1
    assert workers[0].id == worker_id
    assert workers[0].name == "Alice Smith"


def test_worker_editor_edit_hours(qtbot: QtBot) -> None:
    """Test editing hours per workday."""
    controller = ProjectController()
    controller.new_project("Test Project")

    worker_id = controller.add_worker(name="Bob", hours_per_workday=8.0)

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Edit the hours
    item = editor.workers_table.item(0, 2)
    assert item is not None
    item.setText("6.5")

    # Check controller was updated
    workers = controller.get_workers()
    assert len(workers) == 1
    assert workers[0].id == worker_id
    assert workers[0].hours_per_workday == 6.5


def test_worker_editor_updates_on_project_change(qtbot: QtBot) -> None:
    """Test that editor updates when project changes."""
    controller = ProjectController()
    controller.new_project("Test Project")

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Initially empty
    assert editor.workers_table.rowCount() == 0

    # Add a worker via controller
    controller.add_worker(name="Charlie", hours_per_workday=7.0)

    # Editor should update
    assert editor.workers_table.rowCount() == 1
    item = editor.workers_table.item(0, 0)
    assert item is not None
    assert item.text() == "Charlie"


def test_worker_editor_remove_button_disabled_when_no_selection(
    qtbot: QtBot,
) -> None:
    """Test remove button is disabled when no worker is selected."""
    controller = ProjectController()
    controller.new_project("Test Project")

    controller.add_worker(name="Alice", hours_per_workday=8.0)

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Clear selection
    editor.workers_table.clearSelection()
    editor.workers_table.setCurrentCell(-1, -1)

    # Remove button should be disabled
    assert not editor.remove_worker_button.isEnabled()


def test_worker_editor_edit_optional_fields(qtbot: QtBot) -> None:
    """Test editing optional worker fields."""
    controller = ProjectController()
    controller.new_project("Test Project")

    worker_id = controller.add_worker(name="Dave", hours_per_workday=8.0)

    editor = WorkerEditor(controller)
    qtbot.addWidget(editor)

    # Edit worker_id
    item_1 = editor.workers_table.item(0, 1)
    assert item_1 is not None
    item_1.setText("dave_001")

    # Edit description
    item_3 = editor.workers_table.item(0, 3)
    assert item_3 is not None
    item_3.setText("Senior engineer")

    # Check controller was updated
    workers = controller.get_workers()
    assert len(workers) == 1
    assert workers[0].id == worker_id
    assert workers[0].worker_id == "dave_001"
    assert workers[0].description == "Senior engineer"
