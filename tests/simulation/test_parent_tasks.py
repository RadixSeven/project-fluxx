"""Test simulation with parent tasks (tasks that have children)."""

from datetime import UTC, datetime

import numpy as np

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    NodeId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.simulation.engine import run_single_sample


def test_simulation_with_parent_task_should_skip_parent() -> None:
    """Test that simulation correctly handles parent tasks.

    A parent task has children and duration_distribution=None.
    The simulation should execute the children, not the parent.
    The parent's start/end times are determined by its children.
    """
    # Create a parent task B with two children B.1 and B.2
    task_b = Task(
        id=TaskId("B"),
        title="B",
        description="Parent task",
        duration_distribution=None,  # Parent has no distribution!
        children=[TaskId("B.1"), TaskId("B.2")],
    )

    task_b1 = Task(
        id=TaskId("B.1"),
        title="B.1",
        description="Child 1",
        parent_id=TaskId("B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    task_b2 = Task(
        id=TaskId("B.2"),
        title="B.2",
        description="Child 2",
        parent_id=TaskId("B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create project
    version_id = DAGVersionId("v1")

    persistent_b = PersistentTask(
        id=PersistentObjectId("pB"),
        versions={version_id: task_b},
    )
    persistent_b1 = PersistentTask(
        id=PersistentObjectId("pB.1"),
        versions={version_id: task_b1},
    )
    persistent_b2 = PersistentTask(
        id=PersistentObjectId("pB.2"),
        versions={version_id: task_b2},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            NodeId("B"): PersistentObjectId("pB"),
            NodeId("B.1"): PersistentObjectId("pB.1"),
            NodeId("B.2"): PersistentObjectId("pB.2"),
        },
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={
            PersistentObjectId("pB"): persistent_b,
            PersistentObjectId("pB.1"): persistent_b1,
            PersistentObjectId("pB.2"): persistent_b2,
        },
    )

    # Create workers
    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]

    # Run simulation
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(project, workers, start_date, 0, rng)

    # Simulation should succeed
    assert len(sample.failed_tasks) == 0

    # Should have events for B.1 and B.2 (children), but NOT for B (parent)
    task_ids_in_events = {event.node_id for event in sample.events}
    assert NodeId("B.1") in task_ids_in_events
    assert NodeId("B.2") in task_ids_in_events
    # Parent task B should not have start/complete events
    # (its times are inferred from children)
