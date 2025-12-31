"""Test simulation with a realistic project structure matching test_prj.json."""

from datetime import UTC, datetime

from fluxx.data.models import (
    DAG,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
    NodeId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    ShiftedLognormal,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.simulation.engine import SimulationEngine


def test_test_prj_json_structure() -> None:
    """Test simulation with exact structure from test_prj.json.

    Structure:
    - Task A: standalone task
    - Task B: parent task with children B.1, B.2, B.3
      - B.1: child, depends on B.START
      - B.2: child, depends on B.START
      - B.3: child, depends on B.START and B.1.END
    - Task C: depends on B.END
    """
    # Create Task A - standalone task
    task_a = Task(
        id=TaskId("A"),
        title="A",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )

    # Create Task B - parent task
    task_b = Task(
        id=TaskId("B"),
        title="B",
        description="",
        duration_distribution=None,  # Parent has no distribution
        children=[TaskId("B.1"), TaskId("B.2"), TaskId("B.3")],
        dependencies=[
            # Parent depends on all children ending
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=NodeId("B.1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=NodeId("B.2"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=NodeId("B.3"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )

    # Create B.1 - child of B
    task_b1 = Task(
        id=TaskId("B.1"),
        title="B.1",
        description="",
        parent_id=TaskId("B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            # Child depends on parent starting
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=NodeId("B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create B.2 - child of B
    task_b2 = Task(
        id=TaskId("B.2"),
        title="B.2",
        description="",
        parent_id=TaskId("B"),
        duration_distribution=ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0),
        dependencies=[
            # Child depends on parent starting
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=NodeId("B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create B.3 - child of B
    task_b3 = Task(
        id=TaskId("B.3"),
        title="B.3",
        description="",
        parent_id=TaskId("B"),
        duration_distribution=ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0),
        dependencies=[
            # Child depends on parent starting
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=NodeId("B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            # B.3 also depends on B.1 ending
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=NodeId("B.1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )

    # Create Task C - depends on B ending
    task_c = Task(
        id=TaskId("C"),
        title="C",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=NodeId("B"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create project
    version_id = DAGVersionId("v1")

    persistent_a = PersistentTask(
        id=PersistentObjectId("pA"),
        versions={version_id: task_a},
    )
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
    persistent_b3 = PersistentTask(
        id=PersistentObjectId("pB.3"),
        versions={version_id: task_b3},
    )
    persistent_c = PersistentTask(
        id=PersistentObjectId("pC"),
        versions={version_id: task_c},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            NodeId("A"): PersistentObjectId("pA"),
            NodeId("B"): PersistentObjectId("pB"),
            NodeId("B.1"): PersistentObjectId("pB.1"),
            NodeId("B.2"): PersistentObjectId("pB.2"),
            NodeId("B.3"): PersistentObjectId("pB.3"),
            NodeId("C"): PersistentObjectId("pC"),
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
            PersistentObjectId("pA"): persistent_a,
            PersistentObjectId("pB"): persistent_b,
            PersistentObjectId("pB.1"): persistent_b1,
            PersistentObjectId("pB.2"): persistent_b2,
            PersistentObjectId("pB.3"): persistent_b3,
            PersistentObjectId("pC"): persistent_c,
        },
    )

    # Create workers
    workers = [
        Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0),
        Worker(id=WorkerId("w2"), name="Worker 2", hours_per_workday=8.0),
    ]

    # Run simulation with 5 samples
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    engine = SimulationEngine(num_samples=5, start_date=start_date)

    samples = engine.run(project, workers)

    # All 5 samples should succeed (no worker constraints to cause failure)
    assert len(samples) == 5

    for i, sample in enumerate(samples):
        assert len(sample.failed_tasks) == 0, (
            f"Sample {i} failed with tasks: {sample.failed_tasks}"
        )

        # All leaf tasks should have events (A, B.1, B.2, B.3, C)
        # Parent B should not have events
        task_ids_in_events = {event.node_id for event in sample.events}

        assert NodeId("A") in task_ids_in_events, f"Sample {i} missing task A"
        assert NodeId("B.1") in task_ids_in_events, f"Sample {i} missing task B.1"
        assert NodeId("B.2") in task_ids_in_events, f"Sample {i} missing task B.2"
        assert NodeId("B.3") in task_ids_in_events, f"Sample {i} missing task B.3"
        assert NodeId("C") in task_ids_in_events, f"Sample {i} missing task C"

        # Parent B should not have events (never executed)
        assert NodeId("B") not in task_ids_in_events, (
            f"Sample {i} should not have events for parent task B"
        )

        # Verify all events have valid types
        for event in sample.events:
            assert event.event_type in ["start", "complete"], (
                f"Invalid event type: {event.event_type}"
            )
