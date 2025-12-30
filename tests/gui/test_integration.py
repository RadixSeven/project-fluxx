"""Integration tests for complete user workflows."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    NodeId,
    PossibleWorld,
    PossibleWorldId,
    Triangular,
)
from fluxx.gui.main_window import MainWindow


def test_create_and_edit_task_workflow(qtbot: QtBot) -> None:
    """Test complete workflow: create project, add task, edit task."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    # Create new project
    controller.new_project("Integration Test Project")

    # Create a task
    task_id = controller.create_task(
        title="Implement Feature",
        description="Add new feature to the app",
        duration_distribution=Triangular(min=2.0, mode=5.0, max=10.0),
    )

    # Select the task
    controller.select_node(NodeId(task_id))

    # Verify task editor is showing
    assert window.editor_panel.stack.currentWidget() == window.editor_panel.task_editor

    # Verify task is loaded
    assert window.editor_panel.task_editor.current_task_id == task_id

    # Update task via controller
    controller.update_task(
        task_id=task_id,
        title="Implement Advanced Feature",
        description="Add advanced feature with testing",
    )

    # Verify update reflected in project
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task_id)]
    task = project.persistent_tasks[persistent_id].versions[current_version]
    assert task.title == "Implement Advanced Feature"
    assert task.description == "Add advanced feature with testing"


def test_create_task_with_dependency_workflow(qtbot: QtBot) -> None:
    """Test workflow: create two tasks and add dependency."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("Dependency Test Project")

    # Create two tasks
    task1_id = controller.create_task(
        title="Design System",
        description="Design the system architecture",
        duration_distribution=Triangular(min=5.0, mode=8.0, max=12.0),
    )

    task2_id = controller.create_task(
        title="Implement System",
        description="Implement based on design",
        duration_distribution=Triangular(min=10.0, mode=15.0, max=25.0),
    )

    # Add dependency: task2 depends on task1
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId(task1_id),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task2_id), dep)

    # Verify dependency exists
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task2_id)]
    task2 = project.persistent_tasks[persistent_id].versions[current_version]
    assert len(task2.dependencies) == 1
    assert task2.dependencies[0].target_node_id == NodeId(task1_id)


def test_create_branch_workflow(qtbot: QtBot) -> None:
    """Test workflow: create branch with possible worlds."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("Branch Test Project")

    # Create a branch
    branch_id = controller.create_branch(
        title="Technology Choice",
        description="Choose between different technologies",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="Use Framework A",
                description="Go with Framework A",
                weight=3.0,
            ),
            PossibleWorld(
                id=PossibleWorldId("pw_002"),
                title="Use Framework B",
                description="Go with Framework B",
                weight=2.0,
            ),
        ],
    )

    # Select the branch
    controller.select_node(NodeId(branch_id))

    # Verify branch editor is showing
    assert (
        window.editor_panel.stack.currentWidget() == window.editor_panel.branch_editor
    )

    # Verify branch is loaded
    assert window.editor_panel.branch_editor.current_branch_id == branch_id


def test_undo_redo_workflow(qtbot: QtBot) -> None:
    """Test undo/redo functionality."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("Undo Test Project")

    # Create a task
    task_id = controller.create_task(
        title="Original Task",
        description="Original description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update the task
    controller.update_task(task_id=task_id, title="Updated Task")

    # Verify update
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task_id)]
    task = project.persistent_tasks[persistent_id].versions[current_version]
    assert task.title == "Updated Task"

    # Undo
    controller.undo()

    # Verify reverted to original
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task_id)]
    task = project.persistent_tasks[persistent_id].versions[current_version]
    assert task.title == "Original Task"

    # Redo
    controller.redo()

    # Verify back to updated
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task_id)]
    task = project.persistent_tasks[persistent_id].versions[current_version]
    assert task.title == "Updated Task"


def test_save_and_load_workflow(qtbot: QtBot) -> None:
    """Test save and load project workflow."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("Save Test Project")

    # Create some content
    task_id = controller.create_task(
        title="Test Task",
        description="Task for saving",
        duration_distribution=Triangular(min=1.0, mode=3.0, max=5.0),
    )

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test_project.fluxx"

        # Save project
        controller.save_project_as(file_path)

        # Create a new window and load the project
        new_window = MainWindow()
        qtbot.addWidget(new_window)
        new_controller = new_window.controller

        new_controller.open_project(file_path)

        # Verify project loaded correctly
        project = new_controller.get_project()
        assert project.metadata.name == "Save Test Project"

        # Verify task exists
        assert NodeId(task_id) in project.dag.node_map
        persistent_id = project.dag.node_map[NodeId(task_id)]
        assert persistent_id in project.persistent_tasks


def test_worker_management_workflow(qtbot: QtBot) -> None:
    """Test worker management workflow."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("Worker Test Project")

    # Add workers
    worker1_id = controller.add_worker(name="Alice", hours_per_workday=8.0)
    worker2_id = controller.add_worker(name="Bob", hours_per_workday=6.0)

    # Verify workers exist
    workers = controller.get_workers()
    assert len(workers) == 2
    assert workers[0].name == "Alice"
    assert workers[1].name == "Bob"

    # Update worker
    controller.update_worker(worker_id=worker1_id, hours_per_workday=7.0)

    # Verify update
    workers = controller.get_workers()
    assert workers[0].hours_per_workday == 7.0

    # Remove worker
    controller.remove_worker(worker2_id)

    # Verify removal
    workers = controller.get_workers()
    assert len(workers) == 1
    assert workers[0].id == worker1_id


def test_dag_and_list_view_switching(qtbot: QtBot) -> None:
    """Test switching between DAG and list views."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("View Switching Test")

    # Create some tasks
    controller.create_task(
        title="Task 1",
        description="First task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    controller.create_task(
        title="Task 2",
        description="Second task",
        duration_distribution=Triangular(min=2.0, mode=4.0, max=6.0),
    )

    # Initially should be on DAG view
    assert window.dag_panel.view_stack.currentWidget() == window.dag_panel.dag_view

    # Switch to list view
    window.dag_panel.control_bar.view_toggle_button.click()

    # Should now be on list view
    assert window.dag_panel.view_stack.currentWidget() == window.dag_panel.list_view

    # Verify list shows tasks
    assert window.dag_panel.list_view.node_list.count() == 2

    # Switch back to DAG view
    window.dag_panel.control_bar.view_toggle_button.click()

    # Should be back on DAG view
    assert window.dag_panel.view_stack.currentWidget() == window.dag_panel.dag_view


def test_dependency_removal_workflow(qtbot: QtBot) -> None:
    """Test removing dependencies between tasks."""
    window = MainWindow()
    qtbot.addWidget(window)
    controller = window.controller

    controller.new_project("Dependency Removal Test")

    # Create tasks with dependency
    task1_id = controller.create_task(
        title="Task 1",
        description="First task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task2_id = controller.create_task(
        title="Task 2",
        description="Second task",
        duration_distribution=Triangular(min=2.0, mode=4.0, max=6.0),
    )

    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=NodeId(task1_id),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task2_id), dep)

    # Verify dependency exists
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task2_id)]
    task2 = project.persistent_tasks[persistent_id].versions[current_version]
    assert len(task2.dependencies) == 1

    # Remove dependency
    controller.remove_dependency(NodeId(task2_id), dep)

    # Verify dependency removed
    project = controller.get_project()
    current_version = project.dag.current_version_id
    persistent_id = project.dag.node_map[NodeId(task2_id)]
    task2 = project.persistent_tasks[persistent_id].versions[current_version]
    assert len(task2.dependencies) == 0
