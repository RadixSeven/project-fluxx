"""Test simulation with dependencies on parent task endpoints."""

from datetime import UTC, datetime

import numpy as np

from fluxx.data.models import (
    DAG,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
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


def test_child_tasks_depend_on_parent_start() -> None:
    """Test child tasks that depend on their parent's START endpoint.

    This matches the structure in test_prj.json where child tasks have
    dependencies like: "child.start >= parent.start".

    Since parent tasks are never executed, we need to handle parent START/END
    dependencies specially.
    """
    # Create parent task B with children B.1 and B.2
    task_b = Task(
        id=TaskId("B"),
        title="B",
        description="Parent task",
        duration_distribution=None,  # Parent has no distribution
        children=[TaskId("B.1"), TaskId("B.2")],
    )

    # Child B.1 depends on parent B's START
    task_b1 = Task(
        id=TaskId("B.1"),
        title="B.1",
        description="Child 1",
        parent_id=TaskId("B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Child B.2 depends on parent B's START
    task_b2 = Task(
        id=TaskId("B.2"),
        title="B.2",
        description="Child 2",
        parent_id=TaskId("B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Parent B depends on all children's END (this is auto-generated)
    task_b.dependencies = [
        Dependency(
            source_endpoint=Endpoint.END,
            target_node_id=TaskId("B.1"),
            target_endpoint=Endpoint.END,
            constraint_type=ConstraintType.GREATER_EQUAL,
        ),
        Dependency(
            source_endpoint=Endpoint.END,
            target_node_id=TaskId("B.2"),
            target_endpoint=Endpoint.END,
            constraint_type=ConstraintType.GREATER_EQUAL,
        ),
    ]

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
            TaskId("B"): PersistentObjectId("pB"),
            TaskId("B.1"): PersistentObjectId("pB.1"),
            TaskId("B.2"): PersistentObjectId("pB.2"),
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

    # Simulation should succeed - children should be able to start
    # even though parent B never starts
    assert len(sample.failed_tasks) == 0, f"Simulation failed: {sample.failed_tasks}"

    # Should have events for B.1 and B.2 (children), but NOT for B (parent)
    task_ids_in_events = {event.node_id for event in sample.events}
    assert TaskId("B.1") in task_ids_in_events
    assert TaskId("B.2") in task_ids_in_events


def test_non_child_waits_for_parent_start() -> None:
    """Test that a non-child task waiting on parent.start waits for a child to start.

    This verifies the correct semantic: parent "starts" when first child starts.
    """
    # Create parent task P with child P.1
    task_p = Task(
        id=TaskId("P"),
        title="P",
        description="Parent task",
        duration_distribution=None,
        children=[TaskId("P.1")],
    )

    task_p1 = Task(
        id=TaskId("P.1"),
        title="P.1",
        description="Child of P",
        parent_id=TaskId("P"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Task X depends on parent P's START (not a child of P)
    task_x = Task(
        id=TaskId("X"),
        title="X",
        description="Task waiting for parent to start",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("P"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Parent P depends on child ending
    task_p.dependencies = [
        Dependency(
            source_endpoint=Endpoint.END,
            target_node_id=TaskId("P.1"),
            target_endpoint=Endpoint.END,
            constraint_type=ConstraintType.GREATER_EQUAL,
        ),
    ]

    # Create project
    version_id = DAGVersionId("v1")

    persistent_p = PersistentTask(
        id=PersistentObjectId("pP"),
        versions={version_id: task_p},
    )
    persistent_p1 = PersistentTask(
        id=PersistentObjectId("pP.1"),
        versions={version_id: task_p1},
    )
    persistent_x = PersistentTask(
        id=PersistentObjectId("pX"),
        versions={version_id: task_x},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("P"): PersistentObjectId("pP"),
            TaskId("P.1"): PersistentObjectId("pP.1"),
            TaskId("X"): PersistentObjectId("pX"),
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
            PersistentObjectId("pP"): persistent_p,
            PersistentObjectId("pP.1"): persistent_p1,
            PersistentObjectId("pX"): persistent_x,
        },
    )

    # Create workers
    workers = [
        Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0),
        Worker(id=WorkerId("w2"), name="Worker 2", hours_per_workday=8.0),
    ]

    # Run simulation
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    rng = np.random.default_rng(seed=42)

    sample = run_single_sample(project, workers, start_date, 0, rng)

    # Simulation should succeed
    assert len(sample.failed_tasks) == 0, f"Simulation failed: {sample.failed_tasks}"

    # All tasks should have completed
    task_ids_in_events = {event.node_id for event in sample.events}
    assert TaskId("P.1") in task_ids_in_events
    assert TaskId("X") in task_ids_in_events

    # Verify timing: X should start after P.1 starts
    p1_start_time = None
    x_start_time = None

    for event in sample.events:
        if event.node_id == TaskId("P.1") and event.event_type == "start":
            p1_start_time = event.timestamp
        if event.node_id == TaskId("X") and event.event_type == "start":
            x_start_time = event.timestamp

    assert p1_start_time is not None, "P.1 should have started"
    assert x_start_time is not None, "X should have started"
    # X can start at same time as P.1 (>= allows equality)
    assert x_start_time >= p1_start_time, "X should start at or after P.1 starts"
