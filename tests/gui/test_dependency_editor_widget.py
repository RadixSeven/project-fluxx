"""Tests for DependencyEditorWidget."""

from collections.abc import Generator

import pytest
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
from fluxx.gui.widgets.editors.dependency_editor_widget import DependencyEditorWidget


@pytest.fixture
def controller(qtbot: QtBot) -> Generator[ProjectController]:
    """Create a ProjectController for testing.

    Args:
        qtbot: QtBot fixture

    Yields:
        ProjectController instance
    """
    ctrl = ProjectController()
    yield ctrl


@pytest.fixture
def task_dependency_editor(
    qtbot: QtBot, controller: ProjectController
) -> Generator[DependencyEditorWidget]:
    """Create a DependencyEditorWidget for task dependencies.

    Args:
        qtbot: QtBot fixture
        controller: ProjectController fixture

    Yields:
        DependencyEditorWidget instance
    """
    editor = DependencyEditorWidget(controller, is_branch=False)
    qtbot.addWidget(editor)
    yield editor


@pytest.fixture
def branch_dependency_editor(
    qtbot: QtBot, controller: ProjectController
) -> Generator[DependencyEditorWidget]:
    """Create a DependencyEditorWidget for branch dependencies.

    Args:
        qtbot: QtBot fixture
        controller: ProjectController fixture

    Yields:
        DependencyEditorWidget instance
    """
    editor = DependencyEditorWidget(controller, is_branch=True)
    qtbot.addWidget(editor)
    yield editor


def test_dependency_editor_initialization_task(
    task_dependency_editor: DependencyEditorWidget,
) -> None:
    """Test that task dependency editor initializes correctly."""
    # Task editor should have source endpoint combo
    assert hasattr(task_dependency_editor, "source_endpoint_combo")
    assert task_dependency_editor.source_endpoint_combo.count() == 2  # Start, End

    # Should have constraint type combo
    assert task_dependency_editor.constraint_type_combo.count() == 2  # >=, =

    # Should have target endpoint combo
    assert task_dependency_editor.target_endpoint_combo.count() == 3  # Start, End, Occ

    # Target should not be selected
    assert task_dependency_editor._target_node_id is None

    # Add button should be disabled initially (no target selected)
    assert not task_dependency_editor.add_button.isEnabled()

    # Default target endpoint should be END (index 1)
    assert task_dependency_editor.target_endpoint_combo.currentIndex() == 1


def test_dependency_editor_initialization_branch(
    branch_dependency_editor: DependencyEditorWidget,
) -> None:
    """Test that branch dependency editor initializes correctly."""
    # Branch editor should NOT have source endpoint combo (always occurrence)
    assert not hasattr(branch_dependency_editor, "source_endpoint_combo")

    # Should have constraint type combo
    assert branch_dependency_editor.constraint_type_combo.count() == 2  # >=, =

    # Should have target endpoint combo
    assert branch_dependency_editor.target_endpoint_combo.count() == 3


def test_dependency_editor_set_target_task(
    task_dependency_editor: DependencyEditorWidget, controller: ProjectController
) -> None:
    """Test setting target node to a task."""
    # Create a task
    task_id = controller.create_task(
        title="Target Task",
        description="Target",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add button should be disabled before target is set
    assert not task_dependency_editor.add_button.isEnabled()

    # Set as target
    task_dependency_editor.set_target_node(NodeId(task_id))

    # Verify target is set
    assert task_dependency_editor._target_node_id == NodeId(task_id)
    assert "Task: Target Task" in task_dependency_editor.target_display.text()

    # Add button should now be enabled
    assert task_dependency_editor.add_button.isEnabled()

    # Note: We don't verify enabled/disabled state of combo items as that
    # requires accessing Qt model internals which vary by Qt version


def test_dependency_editor_set_target_branch(
    task_dependency_editor: DependencyEditorWidget, controller: ProjectController
) -> None:
    """Test setting target node to a branch."""
    from fluxx.data.id_generation import generate_possible_world_id

    # Create a branch
    branch_id = controller.create_branch(
        title="Target Branch",
        description="Target",
        possible_worlds=[
            PossibleWorld(
                id=generate_possible_world_id(), title="Option A", weight=1.0
            ),
        ],
    )

    # Set as target
    task_dependency_editor.set_target_node(NodeId(branch_id))

    # Verify target is set
    assert task_dependency_editor._target_node_id == NodeId(branch_id)
    assert "Branch: Target Branch" in task_dependency_editor.target_display.text()

    # Should auto-select occurrence for branches
    assert task_dependency_editor.target_endpoint_combo.currentIndex() == 2


def test_dependency_editor_get_dependency_task(
    task_dependency_editor: DependencyEditorWidget, controller: ProjectController
) -> None:
    """Test getting configured dependency from task editor."""
    # Create a task
    task_id = controller.create_task(
        title="Target",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Configure dependency
    task_dependency_editor.source_endpoint_combo.setCurrentIndex(1)  # END
    task_dependency_editor.constraint_type_combo.setCurrentIndex(0)  # >=
    task_dependency_editor.set_target_node(NodeId(task_id))
    task_dependency_editor.target_endpoint_combo.setCurrentIndex(0)  # START

    # Get dependency
    dep = task_dependency_editor.get_dependency()

    assert dep is not None
    assert dep.source_endpoint == Endpoint.END
    assert dep.constraint_type == ConstraintType.GREATER_EQUAL
    assert dep.target_node_id == NodeId(task_id)
    assert dep.target_endpoint == Endpoint.START


def test_dependency_editor_get_dependency_branch(
    branch_dependency_editor: DependencyEditorWidget, controller: ProjectController
) -> None:
    """Test getting configured dependency from branch editor."""
    # Create a task
    task_id = controller.create_task(
        title="Target",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Configure dependency
    # Source endpoint is always OCCURRENCE for branches (no combo)
    branch_dependency_editor.constraint_type_combo.setCurrentIndex(1)  # =
    branch_dependency_editor.set_target_node(NodeId(task_id))
    branch_dependency_editor.target_endpoint_combo.setCurrentIndex(1)  # END

    # Get dependency
    dep = branch_dependency_editor.get_dependency()

    assert dep is not None
    assert dep.source_endpoint == Endpoint.OCCURRENCE  # Always for branches
    assert dep.constraint_type == ConstraintType.EQUAL
    assert dep.target_node_id == NodeId(task_id)
    assert dep.target_endpoint == Endpoint.END


def test_dependency_editor_get_dependency_incomplete(
    task_dependency_editor: DependencyEditorWidget,
) -> None:
    """Test getting dependency when target not selected."""
    # Try to get dependency without setting target
    dep = task_dependency_editor.get_dependency()

    # Should return None
    assert dep is None


def test_dependency_editor_load_dependency(
    task_dependency_editor: DependencyEditorWidget, controller: ProjectController
) -> None:
    """Test loading an existing dependency."""
    # Create a task
    task_id = controller.create_task(
        title="Target",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create dependency
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=NodeId(task_id),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.EQUAL,
    )

    # Load dependency
    task_dependency_editor.load_dependency(dep)

    # Verify fields are set
    assert task_dependency_editor.source_endpoint_combo.currentData() == Endpoint.END
    assert task_dependency_editor.constraint_type_combo.currentData() == "="
    assert task_dependency_editor._target_node_id == NodeId(task_id)
    assert task_dependency_editor.target_endpoint_combo.currentData() == Endpoint.START


def test_dependency_editor_clear(
    task_dependency_editor: DependencyEditorWidget,
) -> None:
    """Test clearing the editor."""
    # Set some values
    task_dependency_editor._target_node_id = NodeId("test_node")
    task_dependency_editor.target_display.setText("Test")
    task_dependency_editor.source_endpoint_combo.setCurrentIndex(1)
    task_dependency_editor.constraint_type_combo.setCurrentIndex(1)
    task_dependency_editor.target_endpoint_combo.setCurrentIndex(2)

    # Clear
    task_dependency_editor.clear()

    # Verify cleared
    assert task_dependency_editor._target_node_id is None
    assert "<Not selected>" in task_dependency_editor.target_display.text()
    assert task_dependency_editor.source_endpoint_combo.currentIndex() == 0
    assert task_dependency_editor.constraint_type_combo.currentIndex() == 0
    assert task_dependency_editor.target_endpoint_combo.currentIndex() == 1


def test_dependency_editor_signals(
    task_dependency_editor: DependencyEditorWidget, qtbot: QtBot
) -> None:
    """Test that editor emits appropriate signals."""
    # Track signals
    select_target_signal_count = 0
    dependency_changed_signal_count = 0
    cancelled_signal_count = 0

    def on_select_target() -> None:
        nonlocal select_target_signal_count
        select_target_signal_count += 1

    def on_dependency_changed() -> None:
        nonlocal dependency_changed_signal_count
        dependency_changed_signal_count += 1

    def on_cancelled() -> None:
        nonlocal cancelled_signal_count
        cancelled_signal_count += 1

    task_dependency_editor.select_target_requested.connect(on_select_target)
    task_dependency_editor.dependency_changed.connect(on_dependency_changed)
    task_dependency_editor.cancelled.connect(on_cancelled)

    # Find buttons
    select_button = None
    cancel_button = None
    for child in task_dependency_editor.findChildren(type(task_dependency_editor)):
        from PySide6.QtWidgets import QPushButton

        for button in child.findChildren(QPushButton):
            if button.text() == "Select Target":
                select_button = button
            elif button.text() == "Cancel":
                cancel_button = button

    # Click select target button
    if select_button:
        select_button.click()
        assert select_target_signal_count == 1

    # Change source endpoint
    task_dependency_editor.source_endpoint_combo.setCurrentIndex(1)
    assert dependency_changed_signal_count >= 1

    # Click cancel button
    if cancel_button:
        cancel_button.click()
        assert cancelled_signal_count == 1


def test_dependency_editor_set_target_possible_world(
    qtbot: QtBot, controller: ProjectController
) -> None:
    """Test setting a possible world as target."""
    # Create a branch with possible worlds
    branch_id = controller.create_branch(
        title="Test Branch",
        description="A branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw_001"),
                title="World A",
                description="First world",
                weight=1.0,
            ),
            PossibleWorld(
                id=PossibleWorldId("pw_002"),
                title="World B",
                description="Second world",
                weight=2.0,
            ),
        ],
    )

    # Create dependency editor
    editor = DependencyEditorWidget(controller, is_branch=False)
    qtbot.addWidget(editor)

    # Set target to possible world (format: "branch_id:world_id")
    pw_node_id = NodeId(f"{branch_id}:pw_001")
    editor.set_target_node(pw_node_id)

    # Check display shows possible world
    assert "Possible World: World A" in editor.target_display.text()
    assert "Test Branch" in editor.target_display.text()

    # Check that only occurrence endpoint is enabled
    from PySide6.QtGui import QStandardItemModel

    model = editor.target_endpoint_combo.model()
    assert isinstance(model, QStandardItemModel)
    assert not model.item(0).isEnabled()  # Start disabled
    assert not model.item(1).isEnabled()  # End disabled
    assert model.item(2).isEnabled()  # Occurrence enabled

    # Check that occurrence is selected
    assert editor.target_endpoint_combo.currentData() == Endpoint.OCCURRENCE

    # Verify we can get the dependency
    dep = editor.get_dependency()
    assert dep is not None
    assert str(dep.target_node_id) == f"{branch_id}:pw_001"
    assert dep.target_endpoint == Endpoint.OCCURRENCE
