"""Tests for probabilistic timeline analysis functions."""

from datetime import UTC, datetime

import pytest

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Sample,
    SampleId,
    Task,
    TaskEvent,
    TaskId,
    Triangular,
)
from fluxx.gui.simulation.analysis import (
    DependencyInfo,
    SampleTaskTimes,
    add_parent_task_times,
    calculate_task_statistics,
    compute_parent_times_per_sample,
    compute_time_statistics,
    extract_leaf_task_times,
    extract_timeline_data,
    get_all_tasks_from_project,
    get_parent_processing_order,
    get_task_from_project,
)

# Fixtures


@pytest.fixture
def simple_project() -> Project:
    """Create a simple project with three leaf tasks."""
    version_id = DAGVersionId("v1")

    # Create three leaf tasks
    task_a = Task(
        id=TaskId("A"),
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_b = Task(
        id=TaskId("B"),
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    task_c = Task(
        id=TaskId("C"),
        title="Task C",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create persistent tasks
    persistent_tasks = {
        PersistentObjectId("pa"): PersistentTask(
            id=PersistentObjectId("pa"),
            versions={version_id: task_a},
        ),
        PersistentObjectId("pb"): PersistentTask(
            id=PersistentObjectId("pb"),
            versions={version_id: task_b},
        ),
        PersistentObjectId("pc"): PersistentTask(
            id=PersistentObjectId("pc"),
            versions={version_id: task_c},
        ),
    }

    # Create DAG
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("A"): PersistentObjectId("pa"),
            TaskId("B"): PersistentObjectId("pb"),
            TaskId("C"): PersistentObjectId("pc"),
        },
    )

    # Create project
    project = Project(
        metadata=ProjectMetadata(
            name="Test Project",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks=persistent_tasks,
    )

    return project


@pytest.fixture
def parent_child_project() -> Project:
    """Create a project with parent and child tasks."""
    version_id = DAGVersionId("v1")

    # Create child tasks
    child1 = Task(
        id=TaskId("C1"),
        title="Child 1",
        description="",
        parent_id=TaskId("P"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    child2 = Task(
        id=TaskId("C2"),
        title="Child 2",
        description="",
        parent_id=TaskId("P"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create parent task
    parent = Task(
        id=TaskId("P"),
        title="Parent",
        description="",
        children=[TaskId("C1"), TaskId("C2")],
    )

    # Create persistent tasks
    persistent_tasks = {
        PersistentObjectId("p"): PersistentTask(
            id=PersistentObjectId("p"),
            versions={version_id: parent},
        ),
        PersistentObjectId("c1"): PersistentTask(
            id=PersistentObjectId("c1"),
            versions={version_id: child1},
        ),
        PersistentObjectId("c2"): PersistentTask(
            id=PersistentObjectId("c2"),
            versions={version_id: child2},
        ),
    }

    # Create DAG
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("P"): PersistentObjectId("p"),
            TaskId("C1"): PersistentObjectId("c1"),
            TaskId("C2"): PersistentObjectId("c2"),
        },
    )

    # Create project
    project = Project(
        metadata=ProjectMetadata(
            name="Parent Child Project",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks=persistent_tasks,
    )

    return project


@pytest.fixture
def nested_parent_project() -> Project:
    """Create a project with nested parents (grandparent -> parent -> children)."""
    version_id = DAGVersionId("v1")

    # Create leaf children
    child1 = Task(
        id=TaskId("C1"),
        title="Child 1",
        description="",
        parent_id=TaskId("P1"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )
    child2 = Task(
        id=TaskId("C2"),
        title="Child 2",
        description="",
        parent_id=TaskId("P1"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create parent (which is also a child of grandparent)
    parent1 = Task(
        id=TaskId("P1"),
        title="Parent 1",
        description="",
        parent_id=TaskId("GP"),
        children=[TaskId("C1"), TaskId("C2")],
    )

    # Create second parent at same level
    parent2 = Task(
        id=TaskId("P2"),
        title="Parent 2",
        description="",
        parent_id=TaskId("GP"),
        children=[TaskId("C3")],
    )

    child3 = Task(
        id=TaskId("C3"),
        title="Child 3",
        description="",
        parent_id=TaskId("P2"),
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create grandparent
    grandparent = Task(
        id=TaskId("GP"),
        title="Grandparent",
        description="",
        children=[TaskId("P1"), TaskId("P2")],
    )

    # Create persistent tasks
    persistent_tasks = {
        PersistentObjectId("gp"): PersistentTask(
            id=PersistentObjectId("gp"),
            versions={version_id: grandparent},
        ),
        PersistentObjectId("p1"): PersistentTask(
            id=PersistentObjectId("p1"),
            versions={version_id: parent1},
        ),
        PersistentObjectId("p2"): PersistentTask(
            id=PersistentObjectId("p2"),
            versions={version_id: parent2},
        ),
        PersistentObjectId("c1"): PersistentTask(
            id=PersistentObjectId("c1"),
            versions={version_id: child1},
        ),
        PersistentObjectId("c2"): PersistentTask(
            id=PersistentObjectId("c2"),
            versions={version_id: child2},
        ),
        PersistentObjectId("c3"): PersistentTask(
            id=PersistentObjectId("c3"),
            versions={version_id: child3},
        ),
    }

    # Create DAG
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("GP"): PersistentObjectId("gp"),
            TaskId("P1"): PersistentObjectId("p1"),
            TaskId("P2"): PersistentObjectId("p2"),
            TaskId("C1"): PersistentObjectId("c1"),
            TaskId("C2"): PersistentObjectId("c2"),
            TaskId("C3"): PersistentObjectId("c3"),
        },
    )

    # Create project
    project = Project(
        metadata=ProjectMetadata(
            name="Nested Parent Project",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks=persistent_tasks,
    )

    return project


@pytest.fixture
def simple_samples() -> list[Sample]:
    """Create simple samples with task events."""
    samples = []

    # Sample 0: A and B complete
    sample0 = Sample(
        sample_id=SampleId(0),
        events=[
            TaskEvent(
                node_id=TaskId("A"),
                event_type="start",
                timestamp=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("A"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("B"),
                event_type="start",
                timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("B"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                details={},
            ),
        ],
        failed_tasks=[],
    )
    samples.append(sample0)

    # Sample 1: A and C complete (different tasks)
    sample1 = Sample(
        sample_id=SampleId(1),
        events=[
            TaskEvent(
                node_id=TaskId("A"),
                event_type="start",
                timestamp=datetime(2024, 1, 2, 9, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("A"),
                event_type="complete",
                timestamp=datetime(2024, 1, 2, 11, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("C"),
                event_type="start",
                timestamp=datetime(2024, 1, 2, 11, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("C"),
                event_type="complete",
                timestamp=datetime(2024, 1, 2, 13, 0, tzinfo=UTC),
                details={},
            ),
        ],
        failed_tasks=[],
    )
    samples.append(sample1)

    return samples


# Tests for get_task_from_project


def test_get_task_from_project(simple_project: Project) -> None:
    """Test retrieving a task from project."""
    task = get_task_from_project(TaskId("A"), simple_project)
    assert task.id == TaskId("A")
    assert task.title == "Task A"


def test_get_task_from_project_not_found(simple_project: Project) -> None:
    """Test retrieving non-existent task raises KeyError."""
    with pytest.raises(KeyError, match="not found in node_map"):
        get_task_from_project(TaskId("INVALID"), simple_project)


# Tests for get_all_tasks_from_project


def test_get_all_tasks_from_project(simple_project: Project) -> None:
    """Test retrieving all tasks from project."""
    tasks = get_all_tasks_from_project(simple_project)
    assert len(tasks) == 3
    task_ids = {t.id for t in tasks}
    assert task_ids == {TaskId("A"), TaskId("B"), TaskId("C")}


def test_get_all_tasks_from_parent_child_project(
    parent_child_project: Project,
) -> None:
    """Test retrieving all tasks including parent."""
    tasks = get_all_tasks_from_project(parent_child_project)
    assert len(tasks) == 3
    task_ids = {t.id for t in tasks}
    assert task_ids == {TaskId("P"), TaskId("C1"), TaskId("C2")}


# Tests for extract_leaf_task_times


def test_extract_leaf_task_times(simple_samples: list[Sample]) -> None:
    """Test extracting task times from samples."""
    sample_times_list = extract_leaf_task_times(simple_samples)

    assert len(sample_times_list) == 2

    # Sample 0: A and B
    sample0_times = sample_times_list[0]
    assert TaskId("A") in sample0_times
    assert TaskId("B") in sample0_times
    assert TaskId("C") not in sample0_times

    # Check A's times
    a_start, a_end = sample0_times[TaskId("A")]
    assert a_start == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    assert a_end == datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

    # Sample 1: A and C
    sample1_times = sample_times_list[1]
    assert TaskId("A") in sample1_times
    assert TaskId("B") not in sample1_times
    assert TaskId("C") in sample1_times


def test_extract_leaf_task_times_empty_samples() -> None:
    """Test extracting times from empty samples."""
    sample_times_list = extract_leaf_task_times([])
    assert sample_times_list == []


def test_extract_leaf_task_times_incomplete_events() -> None:
    """Test that tasks with only start or only complete are ignored."""
    sample = Sample(
        sample_id=SampleId(0),
        events=[
            TaskEvent(
                node_id=TaskId("A"),
                event_type="start",
                timestamp=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                details={},
            ),
            # No complete event for A
            TaskEvent(
                node_id=TaskId("B"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                details={},
            ),
            # No start event for B
        ],
        failed_tasks=[],
    )

    sample_times_list = extract_leaf_task_times([sample])
    assert len(sample_times_list) == 1
    assert TaskId("A") not in sample_times_list[0]
    assert TaskId("B") not in sample_times_list[0]


# Tests for compute_parent_times_per_sample


def test_compute_parent_times_per_sample() -> None:
    """Test computing parent times from children."""
    sample_times = SampleTaskTimes(
        {
            TaskId("C1"): (
                datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            ),
            TaskId("C2"): (
                datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
                datetime(2024, 1, 1, 11, 0, tzinfo=UTC),
            ),
        }
    )

    parent_time = compute_parent_times_per_sample(
        TaskId("P"), [TaskId("C1"), TaskId("C2")], sample_times
    )

    assert parent_time is not None
    start, end = parent_time
    # Parent starts when first child starts (9:00)
    assert start == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    # Parent ends when last child ends (11:00)
    assert end == datetime(2024, 1, 1, 11, 0, tzinfo=UTC)


def test_compute_parent_times_no_children_in_sample() -> None:
    """Test parent with no children in sample returns None."""
    sample_times = SampleTaskTimes({})

    parent_time = compute_parent_times_per_sample(
        TaskId("P"), [TaskId("C1"), TaskId("C2")], sample_times
    )

    assert parent_time is None


def test_compute_parent_times_partial_children() -> None:
    """Test parent with only some children in sample."""
    sample_times = SampleTaskTimes(
        {
            TaskId("C1"): (
                datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            ),
            # C2 not in this sample
        }
    )

    parent_time = compute_parent_times_per_sample(
        TaskId("P"), [TaskId("C1"), TaskId("C2")], sample_times
    )

    assert parent_time is not None
    start, end = parent_time
    # Parent uses only C1's times
    assert start == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    assert end == datetime(2024, 1, 1, 10, 0, tzinfo=UTC)


# Tests for get_parent_processing_order


def test_get_parent_processing_order_simple(parent_child_project: Project) -> None:
    """Test parent processing order with simple parent-child."""
    order = get_parent_processing_order(parent_child_project)
    assert order == [TaskId("P")]


def test_get_parent_processing_order_nested(nested_parent_project: Project) -> None:
    """Test parent processing order with nested parents."""
    order = get_parent_processing_order(nested_parent_project)

    # P1 and P2 must come before GP
    # P1 and P2 can be in either order (deterministic via sorted)
    assert len(order) == 3
    assert order[2] == TaskId("GP")  # Grandparent is last
    assert set(order[:2]) == {TaskId("P1"), TaskId("P2")}  # Parents first
    # Check deterministic ordering (sorted by string)
    assert order[:2] == sorted([TaskId("P1"), TaskId("P2")])


def test_get_parent_processing_order_no_parents(simple_project: Project) -> None:
    """Test parent processing order with no parents."""
    order = get_parent_processing_order(simple_project)
    assert order == []


# Tests for add_parent_task_times


def test_add_parent_task_times(parent_child_project: Project) -> None:
    """Test adding parent times to sample times list."""
    # Create sample times with children
    sample_times_list = [
        SampleTaskTimes(
            {
                TaskId("C1"): (
                    datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                    datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                ),
                TaskId("C2"): (
                    datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
                    datetime(2024, 1, 1, 11, 0, tzinfo=UTC),
                ),
            }
        ),
    ]

    add_parent_task_times(sample_times_list, parent_child_project)

    # Parent should now be in the sample times
    assert TaskId("P") in sample_times_list[0]
    parent_start, parent_end = sample_times_list[0][TaskId("P")]
    assert parent_start == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    assert parent_end == datetime(2024, 1, 1, 11, 0, tzinfo=UTC)


def test_add_parent_task_times_nested(nested_parent_project: Project) -> None:
    """Test adding parent times with nested hierarchy."""
    # Create sample times with leaf children only
    sample_times_list = [
        SampleTaskTimes(
            {
                TaskId("C1"): (
                    datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                    datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                ),
                TaskId("C2"): (
                    datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
                    datetime(2024, 1, 1, 11, 0, tzinfo=UTC),
                ),
                TaskId("C3"): (
                    datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                    datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                ),
            }
        ),
    ]

    add_parent_task_times(sample_times_list, nested_parent_project)

    # All parents should be added
    assert TaskId("P1") in sample_times_list[0]
    assert TaskId("P2") in sample_times_list[0]
    assert TaskId("GP") in sample_times_list[0]

    # Check P1 times (from C1 and C2)
    p1_start, p1_end = sample_times_list[0][TaskId("P1")]
    assert p1_start == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    assert p1_end == datetime(2024, 1, 1, 11, 0, tzinfo=UTC)

    # Check P2 times (from C3)
    p2_start, p2_end = sample_times_list[0][TaskId("P2")]
    assert p2_start == datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    assert p2_end == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    # Check GP times (from P1 and P2, which span all children)
    gp_start, gp_end = sample_times_list[0][TaskId("GP")]
    assert gp_start == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    assert gp_end == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


# Tests for compute_time_statistics


def test_compute_time_statistics() -> None:
    """Test computing time statistics from time pairs."""
    time_pairs = [
        (
            datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        ),
        (
            datetime(2024, 1, 2, 9, 0, tzinfo=UTC),
            datetime(2024, 1, 2, 11, 0, tzinfo=UTC),
        ),
        (
            datetime(2024, 1, 3, 9, 0, tzinfo=UTC),
            datetime(2024, 1, 3, 12, 0, tzinfo=UTC),
        ),
    ]

    stats = compute_time_statistics(time_pairs, percentile=90.0)

    # Min start is first start
    assert stats.min_start_time == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    # Max end is last end
    assert stats.max_end_time == datetime(2024, 1, 3, 12, 0, tzinfo=UTC)
    # Percentiles should be computed
    assert stats.percentile_start_time is not None
    assert stats.percentile_end_time is not None


def test_compute_time_statistics_empty_list() -> None:
    """Test compute_time_statistics with empty list raises error."""
    with pytest.raises(ValueError, match="empty list"):
        compute_time_statistics([], percentile=90.0)


def test_compute_time_statistics_invalid_percentile() -> None:
    """Test compute_time_statistics with invalid percentile raises error."""
    time_pairs = [
        (
            datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        ),
    ]

    with pytest.raises(ValueError, match="Percentile must be between"):
        compute_time_statistics(time_pairs, percentile=0.0)

    with pytest.raises(ValueError, match="Percentile must be between"):
        compute_time_statistics(time_pairs, percentile=100.0)


# Tests for calculate_task_statistics


def test_calculate_task_statistics() -> None:
    """Test calculating task statistics from sample times."""
    sample_times_list = [
        SampleTaskTimes(
            {
                TaskId("A"): (
                    datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                    datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                ),
                TaskId("B"): (
                    datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                    datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                ),
            }
        ),
        SampleTaskTimes(
            {
                TaskId("A"): (
                    datetime(2024, 1, 2, 9, 0, tzinfo=UTC),
                    datetime(2024, 1, 2, 11, 0, tzinfo=UTC),
                ),
                # B doesn't occur in this sample
            }
        ),
    ]

    # Create task titles mapping
    task_titles = {TaskId("A"): "Task A", TaskId("B"): "Task B"}

    stats = calculate_task_statistics(
        sample_times_list, num_samples=2, percentile=90.0, task_titles=task_titles
    )

    # A occurs in 2/2 samples
    assert TaskId("A") in stats
    assert stats[TaskId("A")].task_title == "Task A"
    assert stats[TaskId("A")].occurrence_fraction == 1.0
    assert stats[TaskId("A")].time_statistics is not None

    # B occurs in 1/2 samples
    assert TaskId("B") in stats
    assert stats[TaskId("B")].task_title == "Task B"
    assert stats[TaskId("B")].occurrence_fraction == 0.5
    assert stats[TaskId("B")].time_statistics is not None


# Tests for extract_timeline_data


def test_extract_timeline_data(
    simple_project: Project, simple_samples: list[Sample]
) -> None:
    """Test extracting complete timeline data."""
    timeline_data = extract_timeline_data(
        simple_samples, simple_project, percentile=90.0
    )

    assert timeline_data.percentile == 90.0

    # Should have statistics for tasks that occurred
    assert TaskId("A") in timeline_data.task_statistics
    assert TaskId("B") in timeline_data.task_statistics
    assert TaskId("C") in timeline_data.task_statistics

    # A occurs in both samples
    assert timeline_data.task_statistics[TaskId("A")].occurrence_fraction == 1.0

    # B and C each occur in 1/2 samples
    assert timeline_data.task_statistics[TaskId("B")].occurrence_fraction == 0.5
    assert timeline_data.task_statistics[TaskId("C")].occurrence_fraction == 0.5

    # Earliest and latest times should be set
    assert timeline_data.earliest_time is not None
    assert timeline_data.latest_time is not None
    assert timeline_data.earliest_time <= timeline_data.latest_time


def test_extract_timeline_data_with_parent(parent_child_project: Project) -> None:
    """Test extracting timeline data with parent tasks."""
    # Create samples with child events
    samples = [
        Sample(
            sample_id=SampleId(0),
            events=[
                TaskEvent(
                    node_id=TaskId("C1"),
                    event_type="start",
                    timestamp=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                    details={},
                ),
                TaskEvent(
                    node_id=TaskId("C1"),
                    event_type="complete",
                    timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                    details={},
                ),
                TaskEvent(
                    node_id=TaskId("C2"),
                    event_type="start",
                    timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                    details={},
                ),
                TaskEvent(
                    node_id=TaskId("C2"),
                    event_type="complete",
                    timestamp=datetime(2024, 1, 1, 11, 0, tzinfo=UTC),
                    details={},
                ),
            ],
            failed_tasks=[],
        ),
    ]

    timeline_data = extract_timeline_data(
        samples, parent_child_project, percentile=90.0
    )

    # Should have statistics for children
    assert TaskId("C1") in timeline_data.task_statistics
    assert TaskId("C2") in timeline_data.task_statistics

    # Should also have statistics for parent
    assert TaskId("P") in timeline_data.task_statistics
    assert timeline_data.task_statistics[TaskId("P")].occurrence_fraction == 1.0


def test_extract_timeline_data_empty_samples(simple_project: Project) -> None:
    """Test that empty samples raises error."""
    with pytest.raises(ValueError, match="empty samples"):
        extract_timeline_data([], simple_project, percentile=90.0)


def test_extract_timeline_data_invalid_percentile(
    simple_project: Project, simple_samples: list[Sample]
) -> None:
    """Test that invalid percentile raises error."""
    with pytest.raises(ValueError, match="Percentile must be between"):
        extract_timeline_data(simple_samples, simple_project, percentile=0.0)


def test_extract_timeline_data_dependencies() -> None:
    """Test that dependencies are properly extracted with source info."""
    from fluxx.data.models import ConstraintType, Dependency, Endpoint

    version_id = DAGVersionId("v1")

    # Create task A with dependency on task B
    dep_a = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("B"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )

    task_a = Task(
        id=TaskId("A"),
        title="Task A",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        dependencies=[dep_a],
    )

    task_b = Task(
        id=TaskId("B"),
        title="Task B",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create persistent tasks
    persistent_tasks = {
        PersistentObjectId("pa"): PersistentTask(
            id=PersistentObjectId("pa"),
            versions={version_id: task_a},
        ),
        PersistentObjectId("pb"): PersistentTask(
            id=PersistentObjectId("pb"),
            versions={version_id: task_b},
        ),
    }

    # Create DAG
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("A"): PersistentObjectId("pa"),
            TaskId("B"): PersistentObjectId("pb"),
        },
    )

    # Create project
    project = Project(
        metadata=ProjectMetadata(
            name="Dependency Test",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks=persistent_tasks,
    )

    # Create samples
    samples = [
        Sample(
            sample_id=SampleId(0),
            events=[
                TaskEvent(
                    node_id=TaskId("A"),
                    event_type="start",
                    timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                    details={},
                ),
                TaskEvent(
                    node_id=TaskId("A"),
                    event_type="complete",
                    timestamp=datetime(2024, 1, 1, 11, 0, tzinfo=UTC),
                    details={},
                ),
                TaskEvent(
                    node_id=TaskId("B"),
                    event_type="start",
                    timestamp=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                    details={},
                ),
                TaskEvent(
                    node_id=TaskId("B"),
                    event_type="complete",
                    timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                    details={},
                ),
            ],
            failed_tasks=[],
        ),
    ]

    timeline_data = extract_timeline_data(samples, project, percentile=90.0)

    # Should have one dependency
    assert len(timeline_data.dependencies) == 1

    # Check dependency info
    dep_info = timeline_data.dependencies[0]
    assert isinstance(dep_info, DependencyInfo)
    assert dep_info.source_task_id == TaskId("A")
    assert dep_info.dependency.target_node_id == TaskId("B")
    assert dep_info.dependency.source_endpoint == Endpoint.START
    assert dep_info.dependency.target_endpoint == Endpoint.END
