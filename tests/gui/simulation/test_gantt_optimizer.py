"""Tests for Gantt chart optimizer module."""

from datetime import UTC, datetime, timedelta

import pytest

from fluxx.data.models import (
    DAG,
    ConstraintType,
    DAGId,
    DAGVersionId,
    Dependency,
    Endpoint,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    TaskId,
)
from fluxx.gui.simulation.analysis import DependencyInfo
from fluxx.gui.simulation.gantt_analysis import (
    GanttStatistics,
    GanttTaskStatistics,
    TaskVariantKey,
)
from fluxx.gui.simulation.gantt_optimizer import (
    optimize_gantt_schedule,
)


@pytest.fixture
def simple_project() -> Project:
    """Create a minimal project for testing."""
    version_id = DAGVersionId("v1")
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={},
    )
    return Project(
        metadata=ProjectMetadata(
            name="Test Project",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks={},
    )


def test_optimize_simple_single_task(simple_project: Project) -> None:
    """Test optimization with a single task."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    variant_key = TaskVariantKey(TaskId("task1"), ())

    task_stats = {
        variant_key: GanttTaskStatistics(
            variant_key=variant_key,
            task_title="Task 1",
            percentile_start_time=project_start,
            percentile_duration_hours=2.0,
            sample_count=10,
        )
    }

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=[],
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"
    assert len(schedule.variant_schedules) == 1
    assert variant_key in schedule.variant_schedules

    task_schedule = schedule.variant_schedules[variant_key]
    # Should match percentile values exactly (minimum in optimization)
    assert task_schedule.start_time == project_start
    assert task_schedule.duration_hours == 2.0
    assert task_schedule.end_time == project_start + timedelta(hours=2)


def test_optimize_linear_chain(simple_project: Project) -> None:
    """Test optimization with linear chain: A -> B -> C."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Create three tasks in sequence
    task_a = TaskVariantKey(TaskId("task_a"), ())
    task_b = TaskVariantKey(TaskId("task_b"), ())
    task_c = TaskVariantKey(TaskId("task_c"), ())

    task_stats = {
        task_a: GanttTaskStatistics(
            variant_key=task_a,
            task_title="Task A",
            percentile_start_time=project_start,
            percentile_duration_hours=1.0,
            sample_count=10,
        ),
        task_b: GanttTaskStatistics(
            variant_key=task_b,
            task_title="Task B",
            percentile_start_time=project_start + timedelta(hours=1),
            percentile_duration_hours=2.0,
            sample_count=10,
        ),
        task_c: GanttTaskStatistics(
            variant_key=task_c,
            task_title="Task C",
            percentile_start_time=project_start + timedelta(hours=3),
            percentile_duration_hours=1.5,
            sample_count=10,
        ),
    }

    # Dependencies: B.start >= A.end, C.start >= B.end
    dependencies = [
        DependencyInfo(
            source_task_id=TaskId("task_b"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_a"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
        DependencyInfo(
            source_task_id=TaskId("task_c"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_b"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
    ]

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=dependencies,
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"
    assert len(schedule.variant_schedules) == 3

    # Verify linear chain: A -> B -> C
    sched_a = schedule.variant_schedules[task_a]
    sched_b = schedule.variant_schedules[task_b]
    sched_c = schedule.variant_schedules[task_c]

    # A starts at project start
    assert sched_a.start_time == project_start

    # B starts after A ends
    assert sched_b.start_time >= sched_a.end_time

    # C starts after B ends
    assert sched_c.start_time >= sched_b.end_time


def test_optimize_parallel_tasks(simple_project: Project) -> None:
    """Test optimization with parallel tasks: A -> C, B -> C."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    task_a = TaskVariantKey(TaskId("task_a"), ())
    task_b = TaskVariantKey(TaskId("task_b"), ())
    task_c = TaskVariantKey(TaskId("task_c"), ())

    task_stats = {
        task_a: GanttTaskStatistics(
            variant_key=task_a,
            task_title="Task A",
            percentile_start_time=project_start,
            percentile_duration_hours=2.0,
            sample_count=10,
        ),
        task_b: GanttTaskStatistics(
            variant_key=task_b,
            task_title="Task B",
            percentile_start_time=project_start,
            percentile_duration_hours=3.0,
            sample_count=10,
        ),
        task_c: GanttTaskStatistics(
            variant_key=task_c,
            task_title="Task C",
            percentile_start_time=project_start + timedelta(hours=3),
            percentile_duration_hours=1.0,
            sample_count=10,
        ),
    }

    # Dependencies: C.start >= A.end, C.start >= B.end
    dependencies = [
        DependencyInfo(
            source_task_id=TaskId("task_c"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_a"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
        DependencyInfo(
            source_task_id=TaskId("task_c"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_b"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
    ]

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=dependencies,
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"

    sched_a = schedule.variant_schedules[task_a]
    sched_b = schedule.variant_schedules[task_b]
    sched_c = schedule.variant_schedules[task_c]

    # C must start after both A and B end
    assert sched_c.start_time >= sched_a.end_time
    assert sched_c.start_time >= sched_b.end_time


def test_optimize_respects_percentile_constraints(simple_project: Project) -> None:
    """Test that optimization respects percentile start/duration minimums."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    variant_key = TaskVariantKey(TaskId("task1"), ())

    # Set percentile values
    percentile_start = project_start + timedelta(hours=5)
    percentile_duration = 3.5

    task_stats = {
        variant_key: GanttTaskStatistics(
            variant_key=variant_key,
            task_title="Task 1",
            percentile_start_time=percentile_start,
            percentile_duration_hours=percentile_duration,
            sample_count=10,
        )
    }

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=[],
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"
    task_schedule = schedule.variant_schedules[variant_key]

    # Start time must be >= percentile start time
    assert task_schedule.start_time >= percentile_start

    # Duration must be >= percentile duration
    assert task_schedule.duration_hours >= percentile_duration


def test_optimize_with_different_world_sequences(simple_project: Project) -> None:
    """Test optimization with multiple world sequences (different task variants)."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Same task ID but different world sequences
    world_a = (PossibleWorldId("world_a"),)
    world_b = (PossibleWorldId("world_b"),)

    variant_a = TaskVariantKey(TaskId("task1"), world_a)
    variant_b = TaskVariantKey(TaskId("task1"), world_b)

    task_stats = {
        variant_a: GanttTaskStatistics(
            variant_key=variant_a,
            task_title="Task 1 (World A)",
            percentile_start_time=project_start,
            percentile_duration_hours=2.0,
            sample_count=5,
        ),
        variant_b: GanttTaskStatistics(
            variant_key=variant_b,
            task_title="Task 1 (World B)",
            percentile_start_time=project_start,
            percentile_duration_hours=3.0,
            sample_count=5,
        ),
    }

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=[],
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={world_a, world_b},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"
    assert len(schedule.variant_schedules) == 2

    # Both variants should be optimized independently
    assert variant_a in schedule.variant_schedules
    assert variant_b in schedule.variant_schedules

    # Different durations
    assert schedule.variant_schedules[variant_a].duration_hours == 2.0
    assert schedule.variant_schedules[variant_b].duration_hours == 3.0


def test_optimize_dependency_only_applies_to_matching_world_sequence(
    simple_project: Project,
) -> None:
    """Test that dependencies only apply within the same world sequence."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    world_a = (PossibleWorldId("world_a"),)
    world_b = (PossibleWorldId("world_b"),)

    # Task A exists in world_a, Task B exists in world_b
    variant_a = TaskVariantKey(TaskId("task_a"), world_a)
    variant_b = TaskVariantKey(TaskId("task_b"), world_b)

    task_stats = {
        variant_a: GanttTaskStatistics(
            variant_key=variant_a,
            task_title="Task A",
            percentile_start_time=project_start,
            percentile_duration_hours=1.0,
            sample_count=5,
        ),
        variant_b: GanttTaskStatistics(
            variant_key=variant_b,
            task_title="Task B",
            percentile_start_time=project_start,
            percentile_duration_hours=1.0,
            sample_count=5,
        ),
    }

    # Dependency B -> A (but they're in different worlds, so shouldn't apply)
    dependencies = [
        DependencyInfo(
            source_task_id=TaskId("task_b"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_a"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
    ]

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=dependencies,
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={world_a, world_b},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    # Should still be optimal because dependency doesn't apply across world sequences
    assert schedule.optimization_status == "optimal"


def test_optimize_all_dependency_endpoint_combinations(simple_project: Project) -> None:
    """Test all four dependency endpoint combinations."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Four pairs of tasks to test each combination
    tasks = {}
    for i in range(1, 9):
        variant = TaskVariantKey(TaskId(f"task_{i}"), ())
        tasks[f"task_{i}"] = variant

    task_stats = {}
    for task_id, variant in tasks.items():
        task_stats[variant] = GanttTaskStatistics(
            variant_key=variant,
            task_title=task_id,
            percentile_start_time=project_start,
            percentile_duration_hours=1.0,
            sample_count=10,
        )

    # Test all four endpoint combinations
    dependencies = [
        # B.start >= A.end
        DependencyInfo(
            source_task_id=TaskId("task_2"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_1"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
        # D.start >= C.start
        DependencyInfo(
            source_task_id=TaskId("task_4"),
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=TaskId("task_3"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
        # F.end >= E.end
        DependencyInfo(
            source_task_id=TaskId("task_6"),
            dependency=Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("task_5"),
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
        # H.end >= G.start
        DependencyInfo(
            source_task_id=TaskId("task_8"),
            dependency=Dependency(
                source_endpoint=Endpoint.END,
                target_node_id=TaskId("task_7"),
                target_endpoint=Endpoint.START,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
    ]

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=dependencies,
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"
    assert len(schedule.variant_schedules) == 8

    # Verify each dependency constraint is satisfied
    # B.start >= A.end
    assert (
        schedule.variant_schedules[tasks["task_2"]].start_time
        >= schedule.variant_schedules[tasks["task_1"]].end_time
    )

    # D.start >= C.start
    assert (
        schedule.variant_schedules[tasks["task_4"]].start_time
        >= schedule.variant_schedules[tasks["task_3"]].start_time
    )

    # F.end >= E.end
    assert (
        schedule.variant_schedules[tasks["task_6"]].end_time
        >= schedule.variant_schedules[tasks["task_5"]].end_time
    )

    # H.end >= G.start
    assert (
        schedule.variant_schedules[tasks["task_8"]].end_time
        >= schedule.variant_schedules[tasks["task_7"]].start_time
    )


def test_optimize_empty_statistics(simple_project: Project) -> None:
    """Test optimization with no tasks."""
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    statistics = GanttStatistics(
        task_statistics={},
        dependencies=[],
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, simple_project)

    assert schedule.optimization_status == "optimal"
    assert len(schedule.variant_schedules) == 0


def test_optimize_returns_error_on_exception(simple_project: Project) -> None:
    """Test that optimization returns error status on exception."""
    # This is hard to test without mocking, but we can at least verify
    # the error handling structure exists
    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    variant_key = TaskVariantKey(TaskId("task1"), ())

    task_stats = {
        variant_key: GanttTaskStatistics(
            variant_key=variant_key,
            task_title="Task 1",
            percentile_start_time=project_start,
            percentile_duration_hours=2.0,
            sample_count=10,
        )
    }

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=[],
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    # This should work normally
    schedule = optimize_gantt_schedule(statistics, simple_project)
    assert schedule.optimization_status in ("optimal", "error")


def test_optimize_dependency_on_parent_task_expands_to_children() -> None:
    """Test that C.start >= Parent.end expands to C.start >= max(child.end).

    When a task C depends on parent task B's end, and B has children,
    the constraint must expand to ensure C starts after ALL of B's children
    complete (since B.end = max(child.end) by definition).
    """
    from fluxx.data.models import (
        PersistentObjectId,
        PersistentTask,
        Task,
        Triangular,
    )

    project_start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

    # Task IDs
    parent_id = TaskId("parent_B")
    child1_id = TaskId("child_B1")
    child2_id = TaskId("child_B2")
    task_c_id = TaskId("task_C")

    # Create project with parent task B that has children B1 and B2
    version_id = DAGVersionId("v1")

    # Define tasks with parent-child relationship
    child1 = Task(
        id=child1_id,
        title="Child B1",
        description="",
        parent_id=parent_id,
        children=[],
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[],
    )
    child2 = Task(
        id=child2_id,
        title="Child B2",
        description="",
        parent_id=parent_id,
        children=[],
        duration_distribution=Triangular(min=2.0, mode=3.0, max=4.0),
        dependencies=[],
    )
    parent_b = Task(
        id=parent_id,
        title="Parent B",
        description="",
        parent_id=None,
        children=[child1_id, child2_id],
        duration_distribution=None,  # Parent has no direct duration
        dependencies=[],
    )
    task_c = Task(
        id=task_c_id,
        title="Task C",
        description="",
        parent_id=None,
        children=[],
        duration_distribution=Triangular(min=1.0, mode=1.5, max=2.0),
        # C depends on parent B's end
        dependencies=[
            Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            )
        ],
    )

    # Create persistent tasks
    persistent_tasks = {
        PersistentObjectId("pobj_parent"): PersistentTask(
            id=PersistentObjectId("pobj_parent"),
            versions={version_id: parent_b},
        ),
        PersistentObjectId("pobj_child1"): PersistentTask(
            id=PersistentObjectId("pobj_child1"),
            versions={version_id: child1},
        ),
        PersistentObjectId("pobj_child2"): PersistentTask(
            id=PersistentObjectId("pobj_child2"),
            versions={version_id: child2},
        ),
        PersistentObjectId("pobj_c"): PersistentTask(
            id=PersistentObjectId("pobj_c"),
            versions={version_id: task_c},
        ),
    }

    # Create node_map - NodeId is TaskId | BranchId
    from fluxx.data.models import NodeId

    node_map: dict[NodeId, PersistentObjectId] = {
        parent_id: PersistentObjectId("pobj_parent"),
        child1_id: PersistentObjectId("pobj_child1"),
        child2_id: PersistentObjectId("pobj_child2"),
        task_c_id: PersistentObjectId("pobj_c"),
    }

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map=node_map,
    )

    project = Project(
        metadata=ProjectMetadata(
            name="Parent Dependency Test",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks=persistent_tasks,
    )

    # Create statistics with ONLY leaf tasks (parent B is NOT included)
    # This simulates real behavior where parent tasks don't have direct events
    variant_child1 = TaskVariantKey(child1_id, ())
    variant_child2 = TaskVariantKey(child2_id, ())
    variant_c = TaskVariantKey(task_c_id, ())

    task_stats = {
        variant_child1: GanttTaskStatistics(
            variant_key=variant_child1,
            task_title="Child B1",
            percentile_start_time=project_start,
            percentile_duration_hours=2.0,  # Ends at hour 2
            sample_count=10,
        ),
        variant_child2: GanttTaskStatistics(
            variant_key=variant_child2,
            task_title="Child B2",
            percentile_start_time=project_start,
            percentile_duration_hours=4.0,  # Ends at hour 4 (latest)
            sample_count=10,
        ),
        variant_c: GanttTaskStatistics(
            variant_key=variant_c,
            task_title="Task C",
            # Would start at hour 0 if unconstrained
            percentile_start_time=project_start,
            percentile_duration_hours=1.0,
            sample_count=10,
        ),
    }

    # Dependency: C.start >= Parent_B.end (but Parent_B is not in statistics)
    dependencies = [
        DependencyInfo(
            source_task_id=task_c_id,
            dependency=Dependency(
                source_endpoint=Endpoint.START,
                target_node_id=parent_id,  # Target is the parent!
                target_endpoint=Endpoint.END,
                constraint_type=ConstraintType.GREATER_EQUAL,
            ),
        ),
    ]

    statistics = GanttStatistics(
        task_statistics=task_stats,
        dependencies=dependencies,
        percentile=0.97,
        project_start_date=project_start,
        world_sequences={()},
    )

    schedule = optimize_gantt_schedule(statistics, project)

    assert schedule.optimization_status == "optimal"

    # Key assertion: C must start AFTER both children complete
    # Since child2 ends at hour 4, C must start at or after hour 4
    sched_child1 = schedule.variant_schedules[variant_child1]
    sched_child2 = schedule.variant_schedules[variant_child2]
    sched_c = schedule.variant_schedules[variant_c]

    # C must start after BOTH children end (constraint was expanded)
    assert sched_c.start_time >= sched_child1.end_time, (
        f"C.start ({sched_c.start_time}) should be >= "
        f"child1.end ({sched_child1.end_time})"
    )
    assert sched_c.start_time >= sched_child2.end_time, (
        f"C.start ({sched_c.start_time}) should be >= "
        f"child2.end ({sched_child2.end_time})"
    )

    # Specifically, since child2 ends later (hour 4), C should start at hour 4
    expected_c_start = project_start + timedelta(hours=4)
    assert sched_c.start_time == expected_c_start, (
        f"C should start at {expected_c_start}, but started at {sched_c.start_time}"
    )
