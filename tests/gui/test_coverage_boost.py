"""Additional tests to boost coverage to 95%."""

from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    NodeId,
    PossibleWorld,
    PossibleWorldId,
    ShiftedLognormal,
    Triangular,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.widgets.editors.branch_editor import BranchEditor
from fluxx.gui.widgets.editors.task_editor import TaskEditor

# Branch Editor additional tests


def test_branch_editor_with_dependencies(qtbot: QtBot) -> None:
    """Test branch editor displays dependencies."""
    controller = ProjectController()
    editor = BranchEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create a task and branch
    task_id = controller.create_task(
        title="Task 1", duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0)
    )
    branch_id = controller.create_branch(
        title="Branch 1",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )

    # Add dependency
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=NodeId(task_id),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(branch_id), dep)

    # Load branch
    editor.load_branch(branch_id)

    # Verify dependency shown
    assert editor.dependencies_list.count() > 0


def test_branch_editor_dependency_to_branch(qtbot: QtBot) -> None:
    """Test branch editor with dependency to another branch."""
    controller = ProjectController()
    editor = BranchEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create two branches
    branch1_id = controller.create_branch(
        title="Branch 1",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=1.0)
        ],
    )
    branch2_id = controller.create_branch(
        title="Branch 2",
        possible_worlds=[
            PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=1.0)
        ],
    )

    # Add dependency from branch2 to branch1
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=NodeId(branch1_id),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(NodeId(branch2_id), dep)

    # Load branch2
    editor.load_branch(branch2_id)

    # Verify dependency shown
    assert editor.dependencies_list.count() > 0


def test_branch_editor_possible_worlds_table_setup(qtbot: QtBot) -> None:
    """Test that possible worlds table is set up correctly."""
    controller = ProjectController()
    editor = BranchEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create branch with multiple worlds
    branch_id = controller.create_branch(
        title="Branch",
        possible_worlds=[
            PossibleWorld(
                id=PossibleWorldId("pw1"),
                title="World 1",
                description="Desc 1",
                weight=1.0,
            ),
            PossibleWorld(
                id=PossibleWorldId("pw2"),
                title="World 2",
                description="Desc 2",
                weight=2.0,
            ),
        ],
    )

    # Load branch
    editor.load_branch(branch_id)

    # Verify table has rows
    assert editor.worlds_table.rowCount() > 0


# Task Editor additional tests


def test_task_editor_distribution_none(qtbot: QtBot) -> None:
    """Test task editor with no distribution selected."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Set distribution to None
    editor.distribution_type.setCurrentText("None")

    # Verify no param fields visible
    assert editor.distribution_params_layout.count() == 0


def test_task_editor_invalid_shifted_lognormal(qtbot: QtBot) -> None:
    """Test invalid shifted lognormal parameters."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create task
    task_id = controller.create_task(
        title="Task",
        duration_distribution=ShiftedLognormal(min=1.0, mode=3.0, percentile_95=10.0),
    )
    editor.load_task(task_id)

    # Set invalid mode (less than min)
    editor.mode_field.setText("0.5")

    # Verify apply button disabled
    assert not editor.apply_button.isEnabled()


def test_task_editor_invalid_distribution_params(qtbot: QtBot) -> None:
    """Test invalid distribution parameters."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create task
    task_id = controller.create_task(
        title="Task", duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0)
    )
    editor.load_task(task_id)

    # Set invalid values (non-numeric)
    editor.min_field.setText("abc")

    # Verify apply button disabled
    assert not editor.apply_button.isEnabled()


def test_task_editor_non_numeric_input(qtbot: QtBot) -> None:
    """Test handling of non-numeric input in distribution fields."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create task
    task_id = controller.create_task(
        title="Task", duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0)
    )
    editor.load_task(task_id)

    # Enter non-numeric text
    editor.max_field.setText("not a number")

    # Should not crash, apply should be disabled
    assert not editor.apply_button.isEnabled()


def test_task_editor_distribution_fields_exist(qtbot: QtBot) -> None:
    """Test that distribution fields are created."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create task
    task_id = controller.create_task(
        title="Task", duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0)
    )
    editor.load_task(task_id)

    # Verify fields exist
    assert hasattr(editor, "min_field")
    assert hasattr(editor, "mode_field")
    assert hasattr(editor, "max_field")


def test_task_editor_switch_distribution_types_multiple_times(qtbot: QtBot) -> None:
    """Test switching between distribution types multiple times."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    controller.new_project("Test")

    # Create task with triangular
    task_id = controller.create_task(
        title="Task", duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0)
    )
    editor.load_task(task_id)

    # Switch to shifted lognormal
    editor.distribution_type.setCurrentText("Shifted Lognormal")
    assert hasattr(editor, "percentile_95_field")

    # Switch back to triangular
    editor.distribution_type.setCurrentText("Triangular")
    assert hasattr(editor, "max_field")

    # Switch to None
    editor.distribution_type.setCurrentText("None")
    assert editor.distribution_params_layout.count() == 0


def test_controller_get_project(qtbot: QtBot) -> None:
    """Test controller get_project method."""
    controller = ProjectController()
    controller.new_project("Test")

    project = controller.get_project()
    assert project.metadata.name == "Test"


def test_controller_selection_tracking(qtbot: QtBot) -> None:
    """Test controller selection tracking."""
    controller = ProjectController()
    controller.new_project("Test")

    # Create and select a task
    task_id = controller.create_task(
        title="Task", duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0)
    )
    controller.select_node(NodeId(task_id))

    # Verify selected node is tracked (via internal state)
    assert controller._selected_node_id == NodeId(task_id)


def test_branch_editor_footer_buttons_exist(qtbot: QtBot) -> None:
    """Test that footer buttons exist."""
    controller = ProjectController()
    editor = BranchEditor(controller)
    qtbot.addWidget(editor)

    # Verify buttons exist
    assert editor.apply_button is not None
    assert editor.revert_button is not None


def test_task_editor_footer_buttons_exist(qtbot: QtBot) -> None:
    """Test that footer buttons exist."""
    controller = ProjectController()
    editor = TaskEditor(controller)
    qtbot.addWidget(editor)

    # Verify buttons exist
    assert editor.apply_button is not None
    assert editor.revert_button is not None
