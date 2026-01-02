"""Tests for DAG layout algorithm."""

from fluxx.data.models import (
    ConstraintType,
    Dependency,
    Endpoint,
    Triangular,
)
from fluxx.gui.controller import ProjectController
from fluxx.gui.utils.layout import compute_dag_layout


def test_layout_empty_dag() -> None:
    """Test layout with empty DAG."""
    controller = ProjectController()
    project = controller.get_project()

    layout = compute_dag_layout(project)
    assert layout.node_positions == {}
    assert layout.possible_world_positions == {}


def test_layout_single_task() -> None:
    """Test layout with single task."""
    controller = ProjectController()

    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id = task_id
    assert node_id in positions
    # Horizontal layout: x increases with time
    assert positions[node_id].x() >= 0  # Should be at some x position


def test_layout_two_tasks_no_dependency() -> None:
    """Test layout with two independent tasks."""
    controller = ProjectController()

    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id1 = task_id1
    node_id2 = task_id2

    assert node_id1 in positions
    assert node_id2 in positions
    # Both should be at the same x position (layer 0) since no dependencies
    assert positions[node_id1].x() == positions[node_id2].x()


def test_layout_two_tasks_with_dependency() -> None:
    """Test layout with two tasks connected by dependency."""
    controller = ProjectController()

    # Create two tasks
    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Add dependency: Task 1.start >= Task 2.end (Task 1 starts after Task 2 ends)
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id2,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(task_id1, dep)

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id1 = task_id1
    node_id2 = task_id2

    assert node_id1 in positions
    assert node_id2 in positions

    # Task 1 starts after Task 2 ends, so Task 1 should be further right
    assert positions[node_id1].x() > positions[node_id2].x()


def test_layout_three_tasks_chain() -> None:
    """Test layout with three tasks in a chain."""
    controller = ProjectController()

    # Create three tasks
    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id3 = controller.create_task(
        title="Task 3",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Chain: Task 1.start >= Task 2.end, Task 2.start >= Task 3.end
    # This creates a sequence: Task 3 -> Task 2 -> Task 1
    dep12 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id2,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep23 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id3,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    controller.add_dependency(task_id1, dep12)
    controller.add_dependency(task_id2, dep23)

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    node_id1 = task_id1
    node_id2 = task_id2
    node_id3 = task_id3

    assert node_id1 in positions
    assert node_id2 in positions
    assert node_id3 in positions

    # Check layer ordering (time flows left to right)
    assert positions[node_id1].x() > positions[node_id2].x()
    assert positions[node_id2].x() > positions[node_id3].x()


def test_layout_parent_child_tasks() -> None:
    """Test layout with parent and child tasks.

    This test verifies that the layout can handle parent-child relationships,
    which create valid cycles in the node-based graph but not in the endpoint-based
    dependency graph.
    """
    controller = ProjectController()

    # Create a parent task by converting a leaf
    parent_id = controller.create_task(
        title="Parent Task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Convert to parent (creates child with dependencies)
    child_id = controller.convert_to_parent(parent_id, "Child Task")

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    parent_node_id = parent_id
    child_node_id = child_id

    # Both nodes should have positions
    assert parent_node_id in positions
    assert child_node_id in positions

    # Parent and child should not crash the layout
    # (they create cycles in node graph but not endpoint graph)
    # The specific positioning depends on implementation, but both should exist
    assert positions[parent_node_id] is not None
    assert positions[child_node_id] is not None


def test_layout_branch_with_possible_worlds() -> None:
    """Test layout with branch node and possible worlds."""
    controller = ProjectController()

    # Create branch with possible worlds
    branch_id = controller.create_branch(
        title="Branch",
        description="",
        possible_worlds=[],
    )

    # Add possible worlds
    from fluxx.data.models import PossibleWorld, PossibleWorldId

    pw1 = PossibleWorld(id=PossibleWorldId("pw1"), title="World 1", weight=0.5)
    pw2 = PossibleWorld(id=PossibleWorldId("pw2"), title="World 2", weight=0.5)

    project = controller.get_project()
    persistent_id = project.dag.node_map[branch_id]
    persistent_branch = project.persistent_branches[persistent_id]
    current_version = project.dag.current_version_id
    branch = persistent_branch.versions[current_version]
    branch.possible_worlds = [pw1, pw2]

    layout = compute_dag_layout(project)
    positions = layout.node_positions
    pw_positions = layout.possible_world_positions

    # Branch should have position
    assert branch_id in positions

    # Possible worlds should have positions
    from fluxx.data.models import PossibleWorldId

    assert (branch_id, PossibleWorldId("pw1")) in pw_positions
    assert (branch_id, PossibleWorldId("pw2")) in pw_positions


def test_layout_branch_with_dependencies() -> None:
    """Test layout with branch that has dependencies."""
    controller = ProjectController()

    # Create task and branch
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    branch_id = controller.create_branch(
        title="Branch",
        description="",
        possible_worlds=[],
    )

    # Add dependency: branch.occurrence >= task.end
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=task_id,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    controller.add_dependency(branch_id, dep)

    project = controller.get_project()
    layout = compute_dag_layout(project)
    positions = layout.node_positions

    # Both should have positions
    assert task_id in positions
    assert branch_id in positions

    # Branch should be positioned after task (further right)
    assert positions[branch_id].x() > positions[task_id].x()


def test_layout_with_deleted_task_version() -> None:
    """Test layout when a task version is missing from current version."""

    controller = ProjectController()

    # Create a task
    task_id = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    project = controller.get_project()
    persistent_id = project.dag.node_map[task_id]
    persistent_task = project.persistent_tasks[persistent_id]

    # Remove task from current version (simulate deleted task)
    current_version = project.dag.current_version_id
    del persistent_task.versions[current_version]

    # Layout should handle this gracefully (skip the task)
    layout = compute_dag_layout(project)

    # Task should not be in positions
    assert task_id not in layout.node_positions


def test_layout_with_deleted_branch_version() -> None:
    """Test layout when a branch version is missing from current version."""
    controller = ProjectController()

    # Create a branch
    branch_id = controller.create_branch(
        title="Branch",
        description="",
        possible_worlds=[],
    )

    project = controller.get_project()
    persistent_id = project.dag.node_map[branch_id]
    persistent_branch = project.persistent_branches[persistent_id]

    # Remove branch from current version
    current_version = project.dag.current_version_id
    del persistent_branch.versions[current_version]

    # Layout should handle this gracefully (skip the branch)
    layout = compute_dag_layout(project)

    # Branch should not be in positions
    assert branch_id not in layout.node_positions


def test_layout_with_cycle() -> None:
    """Test layout handles cycles gracefully."""

    controller = ProjectController()

    # Create two tasks
    task_id1 = controller.create_task(
        title="Task 1",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_id2 = controller.create_task(
        title="Task 2",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Manually create a cycle by adding dependencies (bypassing validation)
    # Task 1.start >= Task 2.end AND Task 2.start >= Task 1.end
    # This creates a cycle in the endpoint graph
    dep1 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id2,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    dep2 = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=task_id1,
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    project = controller.get_project()

    # Add dependencies directly to bypass validation
    current_version = project.dag.current_version_id
    persistent_id1 = project.dag.node_map[task_id1]
    persistent_id2 = project.dag.node_map[task_id2]

    task1 = project.persistent_tasks[persistent_id1].versions[current_version]
    task2 = project.persistent_tasks[persistent_id2].versions[current_version]

    task1.dependencies.append(dep1)
    task2.dependencies.append(dep2)

    # Layout should handle cycle by falling back to layer 0 for all nodes
    layout = compute_dag_layout(project)

    # Both tasks should have positions (at layer 0)
    assert task_id1 in layout.node_positions
    assert task_id2 in layout.node_positions
