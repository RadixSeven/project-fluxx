"""Tests for ProjectController."""

from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PyQt6.QtCore import QObject
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
from fluxx.gui.controller import ProjectController


class SignalListener(QObject):
    """Helper class to capture Qt signals."""

    def __init__(self) -> None:
        super().__init__()
        self.signals_received: list[tuple[str, object]] = []

    def on_project_changed(self, project: object) -> None:
        """Capture project_changed signal."""
        self.signals_received.append(("project_changed", project))

    def on_selection_changed(self, node_id: object) -> None:
        """Capture selection_changed signal."""
        self.signals_received.append(("selection_changed", node_id))

    def on_file_path_changed(self, path: object) -> None:
        """Capture file_path_changed signal."""
        self.signals_received.append(("file_path_changed", path))

    def on_modified_changed(self, modified: object) -> None:
        """Capture modified_changed signal."""
        self.signals_received.append(("modified_changed", modified))


@pytest.fixture
def controller(qtbot: QtBot) -> Generator[ProjectController]:
    """Create a ProjectController for testing."""
    ctrl = ProjectController()
    # Note: ProjectController is QObject, not QWidget, so we don't add it to qtbot
    yield ctrl


@pytest.fixture
def listener(qtbot: QtBot) -> Generator[SignalListener]:
    """Create a SignalListener for testing."""
    lst = SignalListener()
    # Note: SignalListener is QObject, not QWidget, so we don't add it to qtbot
    yield lst


def test_controller_initialization(controller: ProjectController) -> None:
    """Test that controller initializes with a default project."""
    project = controller.get_project()
    assert project is not None
    assert project.metadata.name == "Untitled"
    assert controller.get_file_path() is None
    assert not controller.is_modified()
    assert controller.get_selected_node_id() is None


def test_new_project(controller: ProjectController, listener: SignalListener) -> None:
    """Test creating a new project."""
    controller.project_changed.connect(listener.on_project_changed)
    controller.file_path_changed.connect(listener.on_file_path_changed)
    controller.modified_changed.connect(listener.on_modified_changed)
    controller.selection_changed.connect(listener.on_selection_changed)

    controller.new_project("Test Project")

    project = controller.get_project()
    assert project.metadata.name == "Test Project"
    assert controller.get_file_path() is None
    assert not controller.is_modified()
    assert controller.get_selected_node_id() is None

    # Check signals
    signal_names = [s[0] for s in listener.signals_received]
    assert "project_changed" in signal_names
    assert "selection_changed" in signal_names


def test_create_task(controller: ProjectController, listener: SignalListener) -> None:
    """Test creating a task."""
    controller.project_changed.connect(listener.on_project_changed)
    controller.modified_changed.connect(listener.on_modified_changed)

    task_id = controller.create_task(
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    assert task_id is not None
    project = controller.get_project()
    assert NodeId(task_id) in project.dag.node_map
    assert controller.is_modified()

    # Check signals
    signal_names = [s[0] for s in listener.signals_received]
    assert "project_changed" in signal_names
    assert "modified_changed" in signal_names


def test_update_task(controller: ProjectController) -> None:
    """Test updating a task."""
    # Create task
    task_id = controller.create_task(
        title="Original",
        description="Original description",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Update task
    controller.update_task(task_id, title="Updated")

    # Verify update
    project = controller.get_project()
    persistent_id = project.dag.node_map[NodeId(task_id)]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert task.title == "Updated"
    assert task.description == "Original description"


def test_create_branch(controller: ProjectController) -> None:
    """Test creating a branch."""
    branch_id = controller.create_branch(
        title="Branch 1",
        description="Test branch",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="Option A"),
        ],
    )

    assert branch_id is not None
    project = controller.get_project()
    assert NodeId(branch_id) in project.dag.node_map
    assert controller.is_modified()


def test_update_branch(controller: ProjectController) -> None:
    """Test updating a branch."""
    # Create branch
    branch_id = controller.create_branch(
        title="Original",
        description="Original description",
    )

    # Update branch
    controller.update_branch(branch_id, title="Updated")

    # Verify update
    project = controller.get_project()
    persistent_id = project.dag.node_map[NodeId(branch_id)]
    branch = project.persistent_branches[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert branch.title == "Updated"


def test_add_dependency(controller: ProjectController) -> None:
    """Test adding a dependency."""
    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task1_id), dep)

    # Verify dependency
    project = controller.get_project()
    persistent_id = project.dag.node_map[NodeId(task1_id)]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep in task.dependencies


def test_remove_dependency(controller: ProjectController) -> None:
    """Test removing a dependency."""
    # Create two tasks
    task1_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task2_id = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task2_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(task1_id), dep)

    # Remove dependency
    controller.remove_dependency(NodeId(task1_id), dep)

    # Verify dependency removed
    project = controller.get_project()
    persistent_id = project.dag.node_map[NodeId(task1_id)]
    task = project.persistent_tasks[persistent_id].versions[
        project.dag.current_version_id
    ]
    assert dep not in task.dependencies


def test_undo_redo(controller: ProjectController) -> None:
    """Test undo/redo operations."""
    # Initially can't undo
    assert not controller.can_undo()
    assert not controller.can_redo()

    # Create task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Can undo, can't redo
    assert controller.can_undo()
    assert not controller.can_redo()

    # Undo
    controller.undo()

    # Task should be gone
    project = controller.get_project()
    assert NodeId(task_id) not in project.dag.node_map

    # Can't undo, can redo
    assert not controller.can_undo()
    assert controller.can_redo()

    # Redo
    controller.redo()

    # Task should be back
    project = controller.get_project()
    assert NodeId(task_id) in project.dag.node_map

    # Can undo, can't redo
    assert controller.can_undo()
    assert not controller.can_redo()


def test_selection(controller: ProjectController, listener: SignalListener) -> None:
    """Test node selection."""
    controller.selection_changed.connect(listener.on_selection_changed)

    # Create task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Select task
    controller.select_node(NodeId(task_id))

    assert controller.get_selected_node_id() == NodeId(task_id)

    # Check signal
    signal_names = [s[0] for s in listener.signals_received]
    assert "selection_changed" in signal_names

    # Clear selection
    controller.select_node(None)
    assert controller.get_selected_node_id() is None


def test_file_operations(controller: ProjectController) -> None:
    """Test file operations (save/load)."""
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Create task
        task_id = controller.create_task(
            title="Task 1",
            duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        )

        # Save project
        controller.save_project_as(file_path)

        assert controller.get_file_path() == file_path
        assert not controller.is_modified()

        # Modify project
        controller.update_task(task_id, title="Updated")
        assert controller.is_modified()

        # Save again
        controller.save_project()
        assert not controller.is_modified()

        # Create new project
        controller.new_project("New Project")

        # Open saved project
        controller.open_project(file_path)

        project = controller.get_project()
        persistent_id = project.dag.node_map[NodeId(task_id)]
        task = project.persistent_tasks[persistent_id].versions[
            project.dag.current_version_id
        ]
        assert task.title == "Updated"
        assert controller.get_file_path() == file_path
        assert not controller.is_modified()


def test_save_without_path_raises_error(controller: ProjectController) -> None:
    """Test that saving without a file path raises error."""
    # Create new project (no file path)
    controller.new_project("Test")

    with pytest.raises(ValueError, match="No file path set"):
        controller.save_project()


def test_modified_state_tracking(controller: ProjectController) -> None:
    """Test that modified state is tracked correctly."""
    # Initially not modified
    assert not controller.is_modified()

    # Create task - should be modified
    controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    assert controller.is_modified()

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Save - should not be modified
        controller.save_project_as(file_path)
        assert not controller.is_modified()

        # Undo - should be modified again
        controller.undo()
        assert controller.is_modified()


def test_signals_emitted_on_operations(
    controller: ProjectController, listener: SignalListener
) -> None:
    """Test that signals are emitted correctly on operations."""
    controller.project_changed.connect(listener.on_project_changed)
    controller.modified_changed.connect(listener.on_modified_changed)
    controller.file_path_changed.connect(listener.on_file_path_changed)

    # Clear initialization signals
    listener.signals_received.clear()

    # Create task
    controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Should emit project_changed and modified_changed
    signal_names = [s[0] for s in listener.signals_received]
    assert "project_changed" in signal_names
    assert "modified_changed" in signal_names

    listener.signals_received.clear()

    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.fluxx"

        # Save project
        controller.save_project_as(file_path)

        # Should emit file_path_changed and modified_changed
        signal_names = [s[0] for s in listener.signals_received]
        assert "file_path_changed" in signal_names
        assert "modified_changed" in signal_names
