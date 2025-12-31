from unittest.mock import patch

from pytestqt.qtbot import QtBot

from fluxx.data.models import NodeId, Triangular
from fluxx.gui.main_window import MainWindow


def test_navigation_with_unsaved_changes_cancel(qtbot: QtBot) -> None:
    """Test that cancelling navigation keeps the current node selected."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    # Create two tasks with distributions
    dist = Triangular(min=1, mode=2, max=3)
    task1_id = controller.create_task(title="Task 1", duration_distribution=dist)
    task2_id = controller.create_task(title="Task 2", duration_distribution=dist)

    # Select Task 1
    controller.select_node(NodeId(task1_id))

    # Modify Task 1 in the UI
    window.editor_panel.task_editor.title_field.setText("Task 1 Modified")
    assert window.editor_panel.task_editor.is_dirty()

    # Mock QMessageBox
    with patch("fluxx.gui.panels.editor_panel.QMessageBox") as mock_msg_class:
        mock_instance = mock_msg_class.return_value
        # Mock addButton to return the text itself as a "button object"
        mock_instance.addButton.side_effect = lambda text, role=None: text
        # Simulate clicking Cancel
        # Actually in our code:
        # apply_button = msg.addButton("Apply", QMessageBox.ButtonRole.AcceptRole)
        # revert_button = msg.addButton(
        #     "Revert", QMessageBox.ButtonRole.DestructiveRole
        # )
        # msg.addButton(QMessageBox.StandardButton.Cancel)

        mock_instance.addButton.side_effect = (
            lambda arg, role=None: arg if isinstance(arg, str) else "Cancel"
        )
        mock_instance.clickedButton.return_value = "Cancel"

        # Try to select Task 2
        controller.select_node(NodeId(task2_id))

        # Verify selection didn't change
        assert controller.get_selected_node_id() == NodeId(task1_id)
        assert window.editor_panel.task_editor.is_dirty()


def test_navigation_with_unsaved_changes_revert(qtbot: QtBot) -> None:
    """Test that reverting changes allows navigation and loses changes."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    # Create two tasks
    dist = Triangular(min=1, mode=2, max=3)
    task1_id = controller.create_task(title="Task 1", duration_distribution=dist)
    task2_id = controller.create_task(title="Task 2", duration_distribution=dist)

    # Select Task 1
    controller.select_node(NodeId(task1_id))

    # Modify Task 1
    window.editor_panel.task_editor.title_field.setText("Task 1 Modified")

    # Mock QMessageBox
    with patch("fluxx.gui.panels.editor_panel.QMessageBox") as mock_msg_class:
        mock_instance = mock_msg_class.return_value
        mock_instance.addButton.side_effect = (
            lambda arg, role=None: arg if isinstance(arg, str) else "Cancel"
        )
        mock_instance.clickedButton.return_value = "Revert"

        # Try to select Task 2
        controller.select_node(NodeId(task2_id))

        # Verify selection changed
        assert controller.get_selected_node_id() == NodeId(task2_id)

        # Re-select Task 1 and check title (should be original)
        controller.select_node(NodeId(task1_id))
        assert window.editor_panel.task_editor.title_field.text() == "Task 1"


def test_navigation_with_unsaved_changes_apply(qtbot: QtBot) -> None:
    """Test that applying changes allows navigation and saves changes."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    # Create two tasks
    dist = Triangular(min=1, mode=2, max=3)
    task1_id = controller.create_task(title="Task 1", duration_distribution=dist)
    task2_id = controller.create_task(title="Task 2", duration_distribution=dist)

    # Select Task 1
    controller.select_node(NodeId(task1_id))

    # Modify Task 1
    window.editor_panel.task_editor.title_field.setText("Task 1 Modified")

    # Mock QMessageBox
    with patch("fluxx.gui.panels.editor_panel.QMessageBox") as mock_msg_class:
        mock_instance = mock_msg_class.return_value
        mock_instance.addButton.side_effect = (
            lambda arg, role=None: arg if isinstance(arg, str) else "Cancel"
        )
        mock_instance.clickedButton.return_value = "Apply"

        # Try to select Task 2
        controller.select_node(NodeId(task2_id))

        # Verify selection changed
        assert controller.get_selected_node_id() == NodeId(task2_id)

        # Verify changes were saved in the project
        project = controller.get_project()
        persistent_id = project.dag.node_map[NodeId(task1_id)]
        task = project.persistent_tasks[persistent_id].versions[
            project.dag.current_version_id
        ]
        assert task.title == "Task 1 Modified"


def test_navigation_with_unsaved_changes_apply_failed(qtbot: QtBot) -> None:
    """Test that failed application stops navigation."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    # Create two tasks
    dist = Triangular(min=1, mode=2, max=3)
    task1_id = controller.create_task(title="Task 1", duration_distribution=dist)
    task2_id = controller.create_task(title="Task 2", duration_distribution=dist)

    # Select Task 1
    controller.select_node(NodeId(task1_id))

    # Modify Task 1 with invalid value (empty title)
    window.editor_panel.task_editor.title_field.setText("")
    assert window.editor_panel.task_editor.is_dirty()

    # Mock QMessageBox
    with patch("fluxx.gui.panels.editor_panel.QMessageBox") as mock_msg_class:
        mock_instance = mock_msg_class.return_value
        mock_instance.addButton.side_effect = (
            lambda arg, role=None: arg if isinstance(arg, str) else "Cancel"
        )
        mock_instance.clickedButton.return_value = "Apply"

        # Try to select Task 2
        controller.select_node(NodeId(task2_id))

        # Verify selection DID NOT change because Apply failed (invalid title)
        assert controller.get_selected_node_id() == NodeId(task1_id)
        assert window.editor_panel.task_editor.is_dirty()
