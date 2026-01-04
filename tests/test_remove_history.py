"""Tests for remove_history CLI tool."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from fluxx.data.models import (
    DAG,
    Branch,
    BranchId,
    DAGEvent,
    DAGId,
    DAGVersionId,
    EventId,
    EventType,
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Sample,
    SampleId,
    Simulation,
    SimulationId,
    SimulationStatus,
    Task,
    TaskId,
    Worker,
    WorkerId,
)
from fluxx.data.persistence import load_project, save_project
from fluxx.remove_history import main, remove_history


@pytest.fixture
def project_with_history() -> Project:
    """Create a project with multiple versions and history events."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )

    # Create tasks for two versions
    task_v1 = Task(id=TaskId("t1"), title="Task v1", description="Version 1")
    task_v2 = Task(id=TaskId("t1"), title="Task v2", description="Version 2")

    # Create branch for two versions
    branch_v1 = Branch(
        id=BranchId("b1"),
        title="Branch v1",
        description="Version 1",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )
    branch_v2 = Branch(
        id=BranchId("b1"),
        title="Branch v2",
        description="Version 2",
        possible_worlds=[PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")],
    )

    # Create persistent objects with multiple versions
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={
            DAGVersionId("v1"): task_v1,
            DAGVersionId("v2"): task_v2,
        },
    )
    persistent_branch = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={
            DAGVersionId("v1"): branch_v1,
            DAGVersionId("v2"): branch_v2,
        },
    )

    # Create history events
    event1 = DAGEvent(
        id=EventId("e1"),
        timestamp=now,
        parent_event_id=None,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[TaskId("t1")],
        resulting_dag_version=DAGVersionId("v1"),
    )
    event2 = DAGEvent(
        id=EventId("e2"),
        timestamp=now,
        parent_event_id=EventId("e1"),
        event_type=EventType.NODE_MODIFIED,
        affected_nodes=[TaskId("t1")],
        resulting_dag_version=DAGVersionId("v2"),
    )

    # Create simulation
    simulation = Simulation(
        id=SimulationId("sim1"),
        dag_version_id=DAGVersionId("v1"),
        start_date=now,
        num_samples=100,
        num_parallel_processes=4,
        status=SimulationStatus.COMPLETED,
        completed_samples=100,
        samples=[Sample(sample_id=SampleId(0), events=[], failed_tasks=[])],
    )

    # DAG at version 2
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=DAGVersionId("v2"),
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
            BranchId("b1"): PersistentObjectId("pb1"),
        },
    )

    return Project(
        metadata=metadata,
        dag=dag,
        workers=[Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)],
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        persistent_branches={PersistentObjectId("pb1"): persistent_branch},
        history_events=[event1, event2],
        current_event_id=EventId("e2"),
        simulations=[simulation],
    )


def test_remove_history_clears_events(project_with_history: Project) -> None:
    """Test that history events are cleared."""
    clean_project = remove_history(project_with_history)

    assert clean_project.history_events == []
    assert clean_project.current_event_id is None


def test_remove_history_clears_simulations(project_with_history: Project) -> None:
    """Test that simulations are cleared."""
    clean_project = remove_history(project_with_history)

    assert clean_project.simulations == []


def test_remove_history_keeps_current_version(project_with_history: Project) -> None:
    """Test that only the current version of objects is kept."""
    clean_project = remove_history(project_with_history)

    # Should have one task and one branch
    assert len(clean_project.persistent_tasks) == 1
    assert len(clean_project.persistent_branches) == 1

    # Each should have only one version
    pt = clean_project.persistent_tasks[PersistentObjectId("pt1")]
    assert len(pt.versions) == 1

    pb = clean_project.persistent_branches[PersistentObjectId("pb1")]
    assert len(pb.versions) == 1


def test_remove_history_preserves_current_data(project_with_history: Project) -> None:
    """Test that current version data is preserved correctly."""
    clean_project = remove_history(project_with_history)

    # Get the task from the clean project (it has a new version ID)
    pt = clean_project.persistent_tasks[PersistentObjectId("pt1")]
    task = list(pt.versions.values())[0]

    # Should have the v2 data (current version)
    assert task.title == "Task v2"
    assert task.description == "Version 2"


def test_remove_history_preserves_metadata(project_with_history: Project) -> None:
    """Test that project metadata is preserved."""
    clean_project = remove_history(project_with_history)

    assert clean_project.metadata.name == project_with_history.metadata.name
    assert clean_project.metadata.created == project_with_history.metadata.created


def test_remove_history_preserves_workers(project_with_history: Project) -> None:
    """Test that workers are preserved."""
    clean_project = remove_history(project_with_history)

    assert len(clean_project.workers) == 1
    assert clean_project.workers[0].name == "Alice"


def test_remove_history_preserves_node_map(project_with_history: Project) -> None:
    """Test that the node map is preserved."""
    clean_project = remove_history(project_with_history)

    assert clean_project.dag.node_map == project_with_history.dag.node_map


def test_remove_history_creates_new_version_id(project_with_history: Project) -> None:
    """Test that a new clean version ID is created."""
    clean_project = remove_history(project_with_history)

    # Version ID should end with _clean
    assert clean_project.dag.current_version_id.endswith("_clean")
    assert (
        clean_project.dag.current_version_id
        != project_with_history.dag.current_version_id
    )


def test_cli_basic_usage(project_with_history: Project, tmp_path: Path) -> None:
    """Test CLI basic usage."""
    import sys
    from unittest.mock import patch

    input_path = tmp_path / "input.fluxx"
    output_path = tmp_path / "output.fluxx"

    save_project(project_with_history, input_path)

    with patch.object(
        sys, "argv", ["fluxx-remove-history", str(input_path), str(output_path)]
    ):
        result = main()

    assert result == 0
    assert output_path.exists()

    loaded = load_project(output_path)
    assert loaded.history_events == []


def test_cli_nonexistent_input(tmp_path: Path) -> None:
    """Test CLI with nonexistent input file."""
    import sys
    from unittest.mock import patch

    input_path = tmp_path / "nonexistent.fluxx"
    output_path = tmp_path / "output.fluxx"

    with patch.object(
        sys, "argv", ["fluxx-remove-history", str(input_path), str(output_path)]
    ):
        result = main()

    assert result == 1


def test_cli_same_input_output(project_with_history: Project, tmp_path: Path) -> None:
    """Test CLI rejects same input and output file."""
    import sys
    from unittest.mock import patch

    file_path = tmp_path / "project.fluxx"
    save_project(project_with_history, file_path)

    with patch.object(
        sys, "argv", ["fluxx-remove-history", str(file_path), str(file_path)]
    ):
        result = main()

    assert result == 1


def test_empty_project() -> None:
    """Test remove_history on a project with no tasks or branches."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Empty Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))

    project = Project(
        metadata=metadata,
        dag=dag,
    )

    clean_project = remove_history(project)

    assert clean_project.history_events == []
    assert clean_project.persistent_tasks == {}
    assert clean_project.persistent_branches == {}


def test_cli_save_error(project_with_history: Project, tmp_path: Path) -> None:
    """Test CLI handles save errors gracefully."""
    import sys
    from unittest.mock import patch

    input_path = tmp_path / "input.fluxx"
    # Create a read-only directory for output
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o444)
    output_path = readonly_dir / "output.fluxx"

    save_project(project_with_history, input_path)

    try:
        with patch.object(
            sys, "argv", ["fluxx-remove-history", str(input_path), str(output_path)]
        ):
            result = main()

        assert result == 1
    finally:
        readonly_dir.chmod(0o755)


def test_project_with_deleted_nodes() -> None:
    """Test remove_history when some nodes were deleted in current version."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Project with Deleted Nodes",
        created=now,
        last_modified=now,
    )

    # Task exists in v1 but not in v2 (deleted)
    task = Task(id=TaskId("t1"), title="Deleted Task", description="Was deleted")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("v1"): task},  # Only in v1
    )

    # DAG at v2 (task is deleted)
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=DAGVersionId("v2"),
        node_map={},  # Empty because task was deleted
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
    )

    clean_project = remove_history(project)

    # The persistent task should not be in the clean project
    # because it doesn't exist in the current version
    assert len(clean_project.persistent_tasks) == 0
