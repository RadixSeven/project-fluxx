"""Test simulation with a realistic project structure matching test_prj.json."""

from datetime import UTC, datetime

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
        id=TaskId("t_A"),
        title="A",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )

    # Create Task B - parent task
    task_b = Task(
        id=TaskId("t_B"),
        title="B",
        description="",
        duration_distribution=None,  # Parent has no distribution
        children=[TaskId("t_B.1"), TaskId("t_B.2"), TaskId("t_B.3")],
        dependencies=[
            # Parent depends on all children ending
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t_B.1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t_B.2"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t_B.3"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )

    # Create B.1 - child of B
    task_b1 = Task(
        id=TaskId("t_B.1"),
        title="B.1",
        description="",
        parent_id=TaskId("t_B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            # Child depends on parent starting
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create B.2 - child of B
    task_b2 = Task(
        id=TaskId("t_B.2"),
        title="B.2",
        description="",
        parent_id=TaskId("t_B"),
        duration_distribution=ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0),
        dependencies=[
            # Child depends on parent starting
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create B.3 - child of B
    task_b3 = Task(
        id=TaskId("t_B.3"),
        title="B.3",
        description="",
        parent_id=TaskId("t_B"),
        duration_distribution=ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0),
        dependencies=[
            # Child depends on parent starting
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            # B.3 also depends on B.1 ending
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B.1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )

    # Create Task C - depends on B ending
    task_c = Task(
        id=TaskId("t_C"),
        title="C",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
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
            TaskId("t_A"): PersistentObjectId("pA"),
            TaskId("t_B"): PersistentObjectId("pB"),
            TaskId("t_B.1"): PersistentObjectId("pB.1"),
            TaskId("t_B.2"): PersistentObjectId("pB.2"),
            TaskId("t_B.3"): PersistentObjectId("pB.3"),
            TaskId("t_C"): PersistentObjectId("pC"),
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

        assert TaskId("t_A") in task_ids_in_events, f"Sample {i} missing task A"
        assert TaskId("t_B.1") in task_ids_in_events, f"Sample {i} missing task B.1"
        assert TaskId("t_B.2") in task_ids_in_events, f"Sample {i} missing task B.2"
        assert TaskId("t_B.3") in task_ids_in_events, f"Sample {i} missing task B.3"
        assert TaskId("t_C") in task_ids_in_events, f"Sample {i} missing task C"

        # Parent B should not have events (never executed)
        assert TaskId("t_B") not in task_ids_in_events, (
            f"Sample {i} should not have events for parent task B"
        )

        # Verify all events have valid types
        for event in sample.events:
            assert event.event_type in ["start", "complete"], (
                f"Invalid event type: {event.event_type}"
            )


def test_gantt_chart_with_test_prj_structure() -> None:
    """Test Gantt chart extraction and optimization with test_prj.json structure."""
    # Create the same project as above
    task_a = Task(
        id=TaskId("t_A"),
        title="A",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )

    task_b = Task(
        id=TaskId("t_B"),
        title="B",
        description="",
        duration_distribution=None,
        children=[TaskId("t_B.1"), TaskId("t_B.2"), TaskId("t_B.3")],
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t_B.1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t_B.2"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("t_B.3"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )

    task_b1 = Task(
        id=TaskId("t_B.1"),
        title="B.1",
        description="",
        parent_id=TaskId("t_B"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    task_b2 = Task(
        id=TaskId("t_B.2"),
        title="B.2",
        description="",
        parent_id=TaskId("t_B"),
        duration_distribution=ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    task_b3 = Task(
        id=TaskId("t_B.3"),
        title="B.3",
        description="",
        parent_id=TaskId("t_B"),
        duration_distribution=ShiftedLognormal(min=0.25, mode=6.0, percentile_95=24.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B.1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ],
    )

    task_c = Task(
        id=TaskId("t_C"),
        title="C",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("t_B"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create project
    version_id = DAGVersionId("v1")
    persistent_a = PersistentTask(
        id=PersistentObjectId("pA"), versions={version_id: task_a}
    )
    persistent_b = PersistentTask(
        id=PersistentObjectId("pB"), versions={version_id: task_b}
    )
    persistent_b1 = PersistentTask(
        id=PersistentObjectId("pB.1"), versions={version_id: task_b1}
    )
    persistent_b2 = PersistentTask(
        id=PersistentObjectId("pB.2"), versions={version_id: task_b2}
    )
    persistent_b3 = PersistentTask(
        id=PersistentObjectId("pB.3"), versions={version_id: task_b3}
    )
    persistent_c = PersistentTask(
        id=PersistentObjectId("pC"), versions={version_id: task_c}
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t_A"): PersistentObjectId("pA"),
            TaskId("t_B"): PersistentObjectId("pB"),
            TaskId("t_B.1"): PersistentObjectId("pB.1"),
            TaskId("t_B.2"): PersistentObjectId("pB.2"),
            TaskId("t_B.3"): PersistentObjectId("pB.3"),
            TaskId("t_C"): PersistentObjectId("pC"),
        },
    )

    project = Project(
        metadata=ProjectMetadata(
            name="Test Project",
            created=datetime(2024, 1, 1, tzinfo=UTC),
            last_modified=datetime(2024, 1, 1, tzinfo=UTC),
        ),
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

    # Run simulation
    workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    engine = SimulationEngine(num_samples=10, start_date=start_date)
    samples = engine.run(project, workers)

    # Extract Gantt statistics
    from fluxx.gui.simulation.gantt_analysis import extract_gantt_statistics
    from fluxx.gui.simulation.gantt_optimizer import optimize_gantt_schedule

    statistics = extract_gantt_statistics(samples, project, percentile=0.97)

    # Should have statistics for leaf tasks: A, B.1, B.2, B.3, C
    # But NOT for parent task B (it doesn't have events)
    print(f"\nTask statistics keys: {list(statistics.task_statistics.keys())}")
    print(f"Number of task variants: {len(statistics.task_statistics)}")

    # Verify leaf tasks are present
    leaf_task_ids = {
        TaskId("t_A"),
        TaskId("t_B.1"),
        TaskId("t_B.2"),
        TaskId("t_B.3"),
        TaskId("t_C"),
    }
    found_task_ids = {key.task_id for key in statistics.task_statistics}
    print(f"Found task IDs: {found_task_ids}")

    assert leaf_task_ids.issubset(found_task_ids), (
        f"Missing leaf tasks. Expected {leaf_task_ids}, got {found_task_ids}"
    )

    # Optimize schedule
    schedule = optimize_gantt_schedule(statistics, project)

    print(f"\nSchedule status: {schedule.optimization_status}")
    print(f"Number of scheduled variants: {len(schedule.variant_schedules)}")
    sched_task_ids = {key.task_id for key in schedule.variant_schedules}
    print(f"Scheduled task IDs: {sched_task_ids}")

    # Should have schedules for ALL tasks including parent B
    all_task_ids = {
        TaskId("t_A"),
        TaskId("t_B"),
        TaskId("t_B.1"),
        TaskId("t_B.2"),
        TaskId("t_B.3"),
        TaskId("t_C"),
    }
    scheduled_task_ids = {key.task_id for key in schedule.variant_schedules}

    print(f"\nExpected all tasks: {all_task_ids}")
    print(f"Got scheduled tasks: {scheduled_task_ids}")

    assert all_task_ids == scheduled_task_ids, (
        f"Missing tasks in schedule. Expected {all_task_ids}, got {scheduled_task_ids}"
    )

    # Verify schedule is optimal
    assert schedule.optimization_status == "optimal"

    # Verify parent task B spans its children
    from fluxx.gui.simulation.gantt_analysis import TaskVariantKey

    parent_key = TaskVariantKey(TaskId("t_B"), ())
    child_b1_key = TaskVariantKey(TaskId("t_B.1"), ())
    child_b2_key = TaskVariantKey(TaskId("t_B.2"), ())
    child_b3_key = TaskVariantKey(TaskId("t_B.3"), ())

    parent_sched = schedule.variant_schedules[parent_key]
    child_b1_sched = schedule.variant_schedules[child_b1_key]
    child_b2_sched = schedule.variant_schedules[child_b2_key]
    child_b3_sched = schedule.variant_schedules[child_b3_key]

    # Parent start should be <= earliest child start
    earliest_child_start = min(
        child_b1_sched.start_time,
        child_b2_sched.start_time,
        child_b3_sched.start_time,
    )
    msg = (
        f"Parent start {parent_sched.start_time} should be <= "
        f"earliest child start {earliest_child_start}"
    )
    assert parent_sched.start_time <= earliest_child_start, msg

    # Parent end should be >= latest child end
    latest_child_end = max(
        child_b1_sched.end_time,
        child_b2_sched.end_time,
        child_b3_sched.end_time,
    )
    msg = (
        f"Parent end {parent_sched.end_time} should be >= "
        f"latest child end {latest_child_end}"
    )
    assert parent_sched.end_time >= latest_child_end, msg


def test_gantt_chart_with_loaded_test_prj_json() -> None:
    """Test Gantt chart with actual test_prj.json file."""
    import json
    from pathlib import Path

    # Load test_prj.json
    test_prj_path = Path(__file__).parent.parent.parent / "test_prj.json"
    if not test_prj_path.exists():
        import pytest

        pytest.skip(f"test_prj.json not found at {test_prj_path}")

    with open(test_prj_path) as f:
        project_data = json.load(f)

    # Deserialize to Project
    project = Project.model_validate(project_data)

    # Run simulation using project's workers (required for in-progress tasks)
    workers = list(project.workers)
    if not workers:
        # Fall back to default worker if project has no workers
        workers = [Worker(id=WorkerId("w1"), name="Worker 1", hours_per_workday=8.0)]
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    engine = SimulationEngine(num_samples=10, start_date=start_date)
    samples = engine.run(project, workers)

    # Extract Gantt statistics
    from fluxx.gui.simulation.gantt_analysis import extract_gantt_statistics
    from fluxx.gui.simulation.gantt_optimizer import optimize_gantt_schedule

    statistics = extract_gantt_statistics(samples, project, percentile=0.97)

    print(f"\nTask statistics count: {len(statistics.task_statistics)}")
    stat_task_ids = {k.task_id for k in statistics.task_statistics}
    print(f"Task IDs in statistics: {stat_task_ids}")

    # Optimize schedule
    schedule = optimize_gantt_schedule(statistics, project)

    print(f"\nSchedule status: {schedule.optimization_status}")
    print(f"Number of scheduled variants: {len(schedule.variant_schedules)}")
    task_ids = {key.task_id for key in schedule.variant_schedules}
    print(f"Scheduled task IDs: {task_ids}")

    # Should have optimal schedule
    assert schedule.optimization_status == "optimal"

    # Should have more than just leaf tasks (should include parent tasks)
    expected = len(statistics.task_statistics)
    actual = len(schedule.variant_schedules)
    assert actual >= expected, (
        f"Schedule should have at least as many tasks as statistics. "
        f"Got {actual} schedules from {expected} statistics"
    )
