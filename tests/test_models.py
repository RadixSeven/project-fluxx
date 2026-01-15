"""Tests for data models."""

from datetime import UTC, datetime

import pytest

from fluxx.data.models import (
    DAG,
    Branch,
    BranchId,
    Checkpoint,
    ConstraintType,
    DAGEvent,
    DAGId,
    DAGVersionId,
    Dependency,
    DoneCompletion,
    Endpoint,
    EventId,
    EventType,
    NotStartedCompletion,
    PersistentBranch,
    PersistentObjectId,
    PersistentTask,
    PossibleWorld,
    PossibleWorldId,
    Project,
    ProjectMetadata,
    Sample,
    SampleId,
    ShiftedLognormal,
    Simulation,
    SimulationId,
    SimulationStatus,
    StartedCompletion,
    Task,
    TaskEvent,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)


def test_worker_creation() -> None:
    """Test creating a worker."""
    worker = Worker(
        id=WorkerId("w1"), name="Alice", worker_id="alice_1", hours_per_workday=8.0
    )
    assert worker.name == "Alice"
    assert worker.hours_per_workday == 8.0


def test_worker_optional_id() -> None:
    """Test that worker_id is optional."""
    worker = Worker(id=WorkerId("w1"), name="Bob", hours_per_workday=6.0)
    assert worker.worker_id is None


def test_shifted_lognormal_valid() -> None:
    """Test creating a valid shifted lognormal distribution."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=10.0)
    assert dist.min == 1.0
    assert dist.mode == 5.0
    assert dist.percentile_95 == 10.0


def test_shifted_lognormal_mode_validation() -> None:
    """Test that mode must be > min."""
    with pytest.raises(ValueError, match="mode must be greater than min"):
        ShiftedLognormal(min=5.0, mode=3.0, percentile_95=10.0)


def test_shifted_lognormal_percentile_validation() -> None:
    """Test that percentile_95 must be > min."""
    with pytest.raises(ValueError, match="percentile_95 must be greater than min"):
        ShiftedLognormal(min=10.0, mode=15.0, percentile_95=8.0)


def test_triangular_valid() -> None:
    """Test creating a valid triangular distribution."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    assert dist.min == 1.0
    assert dist.mode == 5.0
    assert dist.max == 10.0


def test_triangular_mode_validation() -> None:
    """Test that mode must be > min."""
    with pytest.raises(ValueError, match="mode must be greater than min"):
        Triangular(min=5.0, mode=3.0, max=10.0)


def test_triangular_max_validation() -> None:
    """Test that max must be > mode."""
    with pytest.raises(ValueError, match="max must be greater than mode"):
        Triangular(min=1.0, mode=8.0, max=7.0)


# PossibleWorld Tests


def test_possible_world_creation() -> None:
    """Test creating a possible world."""
    world = PossibleWorld(
        id=PossibleWorldId("pw1"),
        title="Option A",
        description="First option",
        weight=2.0,
    )
    assert world.id == PossibleWorldId("pw1")
    assert world.title == "Option A"
    assert world.weight == 2.0


def test_possible_world_default_values() -> None:
    """Test possible world default values."""
    world = PossibleWorld(id=PossibleWorldId("pw1"), title="Option A")
    assert world.description == ""
    assert world.weight == 1.0


def test_possible_world_weight_validation() -> None:
    """Test that weight must be positive."""
    with pytest.raises(ValueError, match="weight must be positive"):
        PossibleWorld(id=PossibleWorldId("pw1"), title="Option A", weight=0.0)
    with pytest.raises(ValueError, match="weight must be positive"):
        PossibleWorld(id=PossibleWorldId("pw1"), title="Option A", weight=-1.0)


# Dependency Tests


def test_dependency_creation() -> None:
    """Test creating a dependency."""
    dep = Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=TaskId("task2"),
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    assert dep.source_endpoint == Endpoint.END
    assert dep.target_node_id == TaskId("task2")
    assert dep.constraint_type == ConstraintType.GREATER_EQUAL


def test_dependency_with_occurrence_point() -> None:
    """Test dependency with occurrence point."""
    dep = Dependency(
        source_endpoint=Endpoint.OCCURRENCE,
        target_node_id=BranchId("branch1"),
        target_endpoint=Endpoint.OCCURRENCE,
        constraint_type=ConstraintType.EQUAL,
    )
    assert dep.source_endpoint == Endpoint.OCCURRENCE


# Task Tests


def test_task_creation() -> None:
    """Test creating a task."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
    )
    assert task.id == TaskId("t1")
    assert task.title == "Task 1"
    assert task.node_type == "task"
    assert task.dependencies == []


def test_task_with_distribution() -> None:
    """Test task with duration distribution."""
    dist = Triangular(min=1.0, mode=3.0, max=5.0)
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        duration_distribution=dist,
    )
    assert task.duration_distribution is not None
    assert isinstance(task.duration_distribution, Triangular)
    assert task.duration_distribution.min == 1.0


def test_task_with_dependencies() -> None:
    """Test task with dependencies."""
    dep = Dependency(
        source_endpoint=Endpoint.START,
        target_node_id=TaskId("t2"),
        target_endpoint=Endpoint.END,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        dependencies=[dep],
    )
    assert len(task.dependencies) == 1
    assert task.dependencies[0].target_node_id == TaskId("t2")


def test_task_completion_not_started() -> None:
    """Test task with not started completion."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
    )
    assert isinstance(task.completion, NotStartedCompletion)
    assert task.completion.status == "not_started"


def test_task_completion_started() -> None:
    """Test task with started completion."""
    start_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        completion=StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=start_time,
            hours_logged=4.0,
        ),
    )
    assert isinstance(task.completion, StartedCompletion)
    assert task.completion.status == "started"
    assert task.completion.assignee == WorkerId("w1")
    assert task.completion.start_time == start_time
    assert task.completion.hours_logged == 4.0


def test_task_completion_done() -> None:
    """Test task with done completion."""
    start_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    end_time = datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC)
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="First task",
        completion=DoneCompletion(
            assignee=WorkerId("w1"),
            start_time=start_time,
            hours_logged=8.0,
            end_time=end_time,
        ),
    )
    assert isinstance(task.completion, DoneCompletion)
    assert task.completion.status == "done"
    assert task.completion.assignee == WorkerId("w1")
    assert task.completion.hours_logged == 8.0
    assert task.completion.end_time == end_time


def test_started_completion_hours_logged_validation() -> None:
    """Test that hours_logged must be non-negative for started tasks."""
    with pytest.raises(ValueError, match="hours_logged must be non-negative"):
        StartedCompletion(
            assignee=WorkerId("w1"),
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            hours_logged=-1.0,
        )


def test_done_completion_hours_logged_validation() -> None:
    """Test that hours_logged must be positive for done tasks."""
    with pytest.raises(ValueError, match="hours_logged must be positive"):
        DoneCompletion(
            assignee=WorkerId("w1"),
            start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            hours_logged=0.0,
            end_time=datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC),
        )


def test_done_completion_end_after_start_validation() -> None:
    """Test that end_time must be after start_time."""
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        DoneCompletion(
            assignee=WorkerId("w1"),
            start_time=datetime(2024, 1, 15, 18, 0, 0, tzinfo=UTC),
            hours_logged=8.0,
            end_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        )


# Branch Tests


def test_branch_creation() -> None:
    """Test creating a branch."""
    branch = Branch(
        id=BranchId("b1"),
        title="Decision Point",
        description="Choose option",
    )
    assert branch.id == BranchId("b1")
    assert branch.node_type == "branch"
    assert branch.possible_worlds == []


def test_branch_with_possible_worlds() -> None:
    """Test branch with possible worlds."""
    world1 = PossibleWorld(id=PossibleWorldId("pw1"), title="Option A", weight=1.0)
    world2 = PossibleWorld(id=PossibleWorldId("pw2"), title="Option B", weight=2.0)
    branch = Branch(
        id=BranchId("b1"),
        title="Decision",
        description="Choose",
        possible_worlds=[world1, world2],
    )
    assert len(branch.possible_worlds) == 2
    assert branch.possible_worlds[1].weight == 2.0


def test_branch_chosen_world() -> None:
    """Test branch with chosen world."""
    branch = Branch(
        id=BranchId("b1"),
        title="Decision",
        description="Choose",
        chosen_world_id=PossibleWorldId("pw1"),
    )
    assert branch.chosen_world_id == PossibleWorldId("pw1")


# DAG Tests


def test_dag_creation() -> None:
    """Test creating a DAG."""
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=DAGVersionId("v1"),
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
            BranchId("b1"): PersistentObjectId("pb1"),
        },
    )
    assert dag.id == DAGId("dag1")
    assert dag.current_version_id == DAGVersionId("v1")
    assert len(dag.node_map) == 2


# DAGEvent Tests


def test_dag_event_creation() -> None:
    """Test creating a DAG event."""
    now = datetime.now(UTC)
    event = DAGEvent(
        id=EventId("e1"),
        timestamp=now,
        event_type=EventType.NODE_CREATED,
        affected_nodes=[TaskId("t1")],
        resulting_dag_version=DAGVersionId("v2"),
    )
    assert event.event_type == EventType.NODE_CREATED
    assert len(event.affected_nodes) == 1


def test_dag_event_with_parent() -> None:
    """Test DAG event with parent."""
    now = datetime.now(UTC)
    event = DAGEvent(
        id=EventId("e2"),
        timestamp=now,
        parent_event_id=EventId("e1"),
        event_type=EventType.NODE_MODIFIED,
        resulting_dag_version=DAGVersionId("v3"),
    )
    assert event.parent_event_id == EventId("e1")


# Persistent Object Tests


def test_persistent_task_creation() -> None:
    """Test creating a persistent task."""
    task = Task(id=TaskId("t1"), title="Task", description="Test")
    persistent = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={DAGVersionId("v1"): task},
    )
    assert persistent.id == PersistentObjectId("pt1")
    assert len(persistent.versions) == 1


def test_persistent_branch_creation() -> None:
    """Test creating a persistent branch."""
    branch = Branch(id=BranchId("b1"), title="Branch", description="Test")
    persistent = PersistentBranch(
        id=PersistentObjectId("pb1"),
        versions={DAGVersionId("v1"): branch},
    )
    assert persistent.id == PersistentObjectId("pb1")
    assert len(persistent.versions) == 1


# Simulation Tests


def test_task_event_creation() -> None:
    """Test creating a task event."""
    now = datetime.now(UTC)
    event = TaskEvent(
        timestamp=now,
        node_id=TaskId("t1"),
        event_type="start",
        details={"worker_id": "w1"},
    )
    assert event.node_id == TaskId("t1")
    assert event.details["worker_id"] == "w1"


def test_sample_creation() -> None:
    """Test creating a sample."""
    sample = Sample(
        sample_id=SampleId(1),
        events=[],
        failed_tasks=[],
    )
    assert sample.sample_id == SampleId(1)
    assert len(sample.events) == 0
    assert len(sample.failed_tasks) == 0


def test_sample_with_failure() -> None:
    """Test sample with failed tasks."""
    sample = Sample(
        sample_id=SampleId(1),
        events=[],
        failed_tasks=[TaskId("t3"), TaskId("t4")],
    )
    assert len(sample.failed_tasks) == 2


def test_checkpoint_creation() -> None:
    """Test creating a checkpoint."""
    now = datetime.now(UTC)
    checkpoint = Checkpoint(
        timestamp=now,
        completed_samples=100,
        rng_state=[{"state": "data"}],
    )
    assert checkpoint.completed_samples == 100
    assert len(checkpoint.rng_state) == 1


def test_simulation_creation() -> None:
    """Test creating a simulation."""
    now = datetime.now(UTC)
    sim = Simulation(
        id=SimulationId("sim1"),
        dag_version_id=DAGVersionId("v1"),
        start_date=now,
        num_samples=1000,
        num_parallel_processes=4,
        status=SimulationStatus.RUNNING,
    )
    assert sim.num_samples == 1000
    assert sim.status == SimulationStatus.RUNNING
    assert sim.completed_samples == 0


def test_simulation_with_checkpoint() -> None:
    """Test simulation with checkpoint."""
    now = datetime.now(UTC)
    checkpoint = Checkpoint(
        timestamp=now,
        completed_samples=500,
        rng_state=[],
    )
    sim = Simulation(
        id=SimulationId("sim1"),
        dag_version_id=DAGVersionId("v1"),
        start_date=now,
        num_samples=1000,
        num_parallel_processes=4,
        status=SimulationStatus.INTERRUPTED,
        completed_samples=500,
        last_checkpoint=checkpoint,
    )
    assert sim.last_checkpoint is not None
    assert sim.last_checkpoint.completed_samples == 500


# Project Tests


def test_project_metadata_creation() -> None:
    """Test creating project metadata."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    assert metadata.name == "Test Project"


def test_project_creation() -> None:
    """Test creating a project."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    project = Project(
        metadata=metadata,
        dag=dag,
    )
    assert project.version == "1.3"
    assert project.metadata.name == "Test Project"
    assert len(project.workers) == 0
    assert len(project.simulations) == 0


def test_project_with_workers() -> None:
    """Test project with workers."""
    now = datetime.now(UTC)
    metadata = ProjectMetadata(
        name="Test Project",
        created=now,
        last_modified=now,
    )
    dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
    worker = Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)
    project = Project(
        metadata=metadata,
        dag=dag,
        workers=[worker],
    )
    assert len(project.workers) == 1
    assert project.workers[0].name == "Alice"


def test_type_explode_id_with_invalid_pattern() -> None:
    """Test type_explode_id raises ValueError for invalid ID patterns."""
    from fluxx.data.models import TaskId, type_explode_id

    # Create a TaskId with an invalid pattern that doesn't match any known
    # format. We're intentionally creating an invalid ID to test error handling.
    invalid_id = TaskId("invalid_id_pattern_xyz")

    with pytest.raises(ValueError, match="Unknown dependency target ID pattern"):
        type_explode_id(invalid_id)


def test_extract_node_id_with_task() -> None:
    """Test extract_node_id with a task ID."""
    from fluxx.data.models import extract_node_id

    task_id = TaskId("t1")
    node_id = extract_node_id(task_id)
    assert node_id == task_id


def test_extract_node_id_with_branch() -> None:
    """Test extract_node_id with a branch ID."""
    from fluxx.data.models import BranchId, extract_node_id

    branch_id = BranchId("b1")
    node_id = extract_node_id(branch_id)
    assert node_id == branch_id


def test_extract_node_id_with_possible_world() -> None:
    """Test extract_node_id with a possible world reference."""
    from fluxx.data.models import PossibleWorldReference, extract_node_id

    # Possible world reference format: "branch_id:world_id"
    pw_ref = PossibleWorldReference("b1:pw1")
    node_id = extract_node_id(pw_ref)
    # Should extract the branch ID
    assert node_id == BranchId("b1")


def test_get_dep_id_type_with_task() -> None:
    """Test get_dep_id_type with a task ID."""
    from fluxx.data.models import DependencyTargetIdType, get_dep_id_type

    task_id = TaskId("t1")
    id_type = get_dep_id_type(task_id)
    assert id_type == DependencyTargetIdType.TASK


def test_get_dep_id_type_with_branch() -> None:
    """Test get_dep_id_type with a branch ID."""
    from fluxx.data.models import DependencyTargetIdType, get_dep_id_type

    branch_id = BranchId("b1")
    id_type = get_dep_id_type(branch_id)
    assert id_type == DependencyTargetIdType.BRANCH


def test_get_dep_id_type_with_possible_world() -> None:
    """Test get_dep_id_type with a possible world reference."""
    from fluxx.data.models import (
        DependencyTargetIdType,
        PossibleWorldReference,
        get_dep_id_type,
    )

    pw_ref = PossibleWorldReference("b1:pw1")
    id_type = get_dep_id_type(pw_ref)
    assert id_type == DependencyTargetIdType.POSSIBLE_WORLD_REFERENCE


def test_str_to_node_id_with_task() -> None:
    """Test str_to_node_id with a task ID string."""
    from fluxx.data.models import str_to_node_id

    node_id = str_to_node_id("t1")
    assert node_id == TaskId("t1")


def test_str_to_node_id_with_branch() -> None:
    """Test str_to_node_id with a branch ID string."""
    from fluxx.data.models import str_to_node_id

    node_id = str_to_node_id("b1")
    assert node_id == BranchId("b1")


def test_str_to_node_id_with_possible_world_raises() -> None:
    """Test str_to_node_id raises ValueError for possible world reference."""
    from fluxx.data.models import str_to_node_id

    # Possible world reference is not a valid NodeId (only task or branch)
    with pytest.raises(
        ValueError, match="Cannot convert.*to NodeId: it's not a task or branch ID"
    ):
        str_to_node_id("b1:pw1")


def test_extract_node_id_with_all_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test extract_node_id raises ValueError when type_explode_id returns all None.

    This tests defensive error handling that should never happen in practice.
    """
    from fluxx.data import models

    # Mock type_explode_id to return all None (should never happen in reality)
    def mock_type_explode_id(
        ref: models.DependencyTargetId,
    ) -> tuple[
        models.TaskId | None,
        models.BranchId | None,
        models.PossibleWorldReferencePair | None,
    ]:
        # Return all None - this is an impossible state but tests the
        # defensive error handling
        return None, None, None

    monkeypatch.setattr(models, "type_explode_id", mock_type_explode_id)

    task_id = TaskId("t1")
    with pytest.raises(ValueError, match="Forgot to add branch"):
        models.extract_node_id(task_id)


# Jira integration tests


class TestTaskJiraFields:
    """Tests for Jira-related fields on Task model."""

    def test_task_with_jira_reference_serializes(self) -> None:
        """Test that task with jira_reference serializes correctly."""
        from fluxx.jira.models import JiraIssueKey, JiraReference

        jira_ref = JiraReference(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=1234),
        )
        task = Task(
            id=TaskId("t1"),
            title="Test Task",
            description="Description",
            jira_reference=jira_ref,
            jira_issue_type="Story",
        )
        data = task.model_dump()
        assert "jira_reference" in data
        assert data["jira_reference"]["server_url"] == "https://jira.example.com"
        assert data["jira_reference"]["issue_key"]["project_key"] == "FHIR"
        assert data["jira_reference"]["issue_key"]["issue_number"] == 1234
        assert data["jira_issue_type"] == "Story"

    def test_task_without_jira_reference_allowed(self) -> None:
        """Test that task without jira_reference is valid."""
        task = Task(
            id=TaskId("t1"),
            title="Test Task",
            description="Description",
        )
        assert task.jira_reference is None
        assert task.jira_issue_type is None

    def test_task_jira_reference_deserialization(self) -> None:
        """Test deserializing task with jira_reference."""
        data = {
            "id": "t1",
            "title": "Test Task",
            "description": "Description",
            "jira_reference": {
                "server_url": "https://jira.example.com",
                "issue_key": {"project_key": "TEST", "issue_number": 42},
            },
            "jira_issue_type": "Bug",
        }
        task = Task.model_validate(data)
        assert task.jira_reference is not None
        assert task.jira_reference.server_url == "https://jira.example.com"
        assert task.jira_reference.issue_key.project_key == "TEST"
        assert task.jira_reference.issue_key.issue_number == 42
        assert task.jira_issue_type == "Bug"

    def test_task_jira_issue_type_without_reference(self) -> None:
        """Test that jira_issue_type can be set without jira_reference."""
        task = Task(
            id=TaskId("t1"),
            title="Test Task",
            description="Description",
            jira_issue_type="Epic",
        )
        assert task.jira_reference is None
        assert task.jira_issue_type == "Epic"


class TestWorkerJiraFields:
    """Tests for Jira-related fields on Worker model."""

    def test_worker_with_jira_user_id(self) -> None:
        """Test worker with jira_user_id."""
        worker = Worker(
            id=WorkerId("w1"),
            name="Alice",
            worker_id="alice_1",
            hours_per_workday=8.0,
            jira_user_id="alice123",
        )
        assert worker.jira_user_id == "alice123"

    def test_worker_jira_user_id_defaults_none(self) -> None:
        """Test that jira_user_id defaults to None."""
        worker = Worker(
            id=WorkerId("w1"),
            name="Bob",
            worker_id="bob_1",
            hours_per_workday=8.0,
        )
        assert worker.jira_user_id is None

    def test_worker_jira_user_id_serialization(self) -> None:
        """Test serialization of worker with jira_user_id."""
        worker = Worker(
            id=WorkerId("w1"),
            name="Charlie",
            worker_id="charlie_1",
            hours_per_workday=6.0,
            jira_user_id="charlie_jira",
        )
        data = worker.model_dump()
        assert data["jira_user_id"] == "charlie_jira"

    def test_worker_jira_user_id_deserialization(self) -> None:
        """Test deserialization of worker with jira_user_id."""
        data = {
            "id": "w1",
            "name": "Diana",
            "worker_id": "diana_1",
            "hours_per_workday": 7.5,
            "jira_user_id": "diana_jira_id",
        }
        worker = Worker.model_validate(data)
        assert worker.jira_user_id == "diana_jira_id"


class TestJiraDurationDistribution:
    """Tests for JiraDurationDistribution model."""

    def test_jira_duration_distribution_is_duration_distribution(self) -> None:
        """Test that JiraDurationDistribution is a DurationDistribution."""
        from fluxx.data.models import JiraDurationDistribution

        dist = JiraDurationDistribution(original_estimate_seconds=3600)
        # Should be a valid DurationDistribution subclass
        assert hasattr(dist, "original_estimate_seconds")

    def test_jira_duration_distribution_all_optional(self) -> None:
        """Test that all fields are optional."""
        from fluxx.data.models import JiraDurationDistribution

        dist = JiraDurationDistribution()
        assert dist.original_estimate_seconds is None
        assert dist.story_points is None
        assert dist.remaining_estimate_seconds is None

    def test_jira_duration_distribution_with_all_fields(self) -> None:
        """Test with all fields populated."""
        from fluxx.data.models import JiraDurationDistribution

        dist = JiraDurationDistribution(
            original_estimate_seconds=28800,  # 8 hours
            story_points=5.0,
            remaining_estimate_seconds=14400,  # 4 hours
        )
        assert dist.original_estimate_seconds == 28800
        assert dist.story_points == 5.0
        assert dist.remaining_estimate_seconds == 14400

    def test_jira_duration_distribution_serialization(self) -> None:
        """Test JSON serialization."""
        from fluxx.data.models import JiraDurationDistribution

        dist = JiraDurationDistribution(
            original_estimate_seconds=3600,
            story_points=3.0,
        )
        data = dist.model_dump()
        assert data["original_estimate_seconds"] == 3600
        assert data["story_points"] == 3.0
        assert data["remaining_estimate_seconds"] is None

    def test_jira_duration_distribution_deserialization(self) -> None:
        """Test JSON deserialization."""
        from fluxx.data.models import JiraDurationDistribution

        data = {
            "original_estimate_seconds": 7200,
            "story_points": 2.0,
            "remaining_estimate_seconds": 3600,
        }
        dist = JiraDurationDistribution.model_validate(data)
        assert dist.original_estimate_seconds == 7200
        assert dist.story_points == 2.0
        assert dist.remaining_estimate_seconds == 3600

    def test_task_with_jira_duration_distribution(self) -> None:
        """Test that Task can have JiraDurationDistribution."""
        from fluxx.data.models import JiraDurationDistribution

        dist = JiraDurationDistribution(original_estimate_seconds=3600)
        task = Task(
            id=TaskId("t1"),
            title="Test Task",
            description="Description",
            duration_distribution=dist,
        )
        assert task.duration_distribution is not None
        assert isinstance(task.duration_distribution, JiraDurationDistribution)
        assert task.duration_distribution.original_estimate_seconds == 3600


class TestProjectJiraConfig:
    """Tests for jira_config field on Project model."""

    def test_project_jira_config_defaults_none(self) -> None:
        """Test that jira_config defaults to None."""
        now = datetime.now(UTC)
        metadata = ProjectMetadata(
            name="Test Project",
            created=now,
            last_modified=now,
        )
        dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
        project = Project(
            metadata=metadata,
            dag=dag,
        )
        assert project.jira_config is None

    def test_project_with_jira_config(self) -> None:
        """Test project with jira_config."""
        from fluxx.jira.models import (
            EstimateSource,
            JiraConfig,
            JiraDurationHistoryEntry,
            JiraIssueKey,
            JiraSyncMetadata,
        )

        now = datetime.now(UTC)
        metadata = ProjectMetadata(
            name="Test Project",
            created=now,
            last_modified=now,
        )
        dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))

        # Create a JiraConfig with sync metadata
        history_entry = JiraDurationHistoryEntry(
            server_url="https://jira.example.com",
            issue_key=JiraIssueKey(project_key="FHIR", issue_number=100),
            issue_type="Story",
            original_estimate_seconds=28800,
            estimate_source=EstimateSource.FROM_ORIGINAL_ESTIMATE,
        )
        sync_metadata = JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=now,
            history_entries=[history_entry],
        )
        jira_config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=sync_metadata,
        )

        project = Project(
            metadata=metadata,
            dag=dag,
            jira_config=jira_config,
        )
        assert project.jira_config is not None
        assert project.jira_config.server_url == "https://jira.example.com"
        assert len(project.jira_config.sync_metadata.history_entries) == 1

    def test_project_jira_config_serialization(self) -> None:
        """Test serialization of project with jira_config."""
        from fluxx.jira.models import (
            JiraConfig,
            JiraSyncMetadata,
        )

        now = datetime.now(UTC)
        metadata = ProjectMetadata(
            name="Test Project",
            created=now,
            last_modified=now,
        )
        dag = DAG(id=DAGId("dag1"), current_version_id=DAGVersionId("v1"))
        sync_metadata = JiraSyncMetadata(
            server_url="https://jira.example.com",
            last_history_sync=now,
            history_entries=[],
        )
        jira_config = JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=sync_metadata,
        )
        project = Project(
            metadata=metadata,
            dag=dag,
            jira_config=jira_config,
        )
        data = project.model_dump(mode="json")
        assert "jira_config" in data
        assert data["jira_config"]["server_url"] == "https://jira.example.com"


class TestDatetimeTimezoneValidation:
    """Tests for datetime timezone validation in models."""

    def test_started_completion_start_time_requires_timezone(self) -> None:
        """StartedCompletion.start_time rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="start_time must have timezone info"):
            StartedCompletion(
                assignee=WorkerId("w1"),
                hours_logged=1.0,
                start_time=naive_dt,
            )

    def test_done_completion_start_time_requires_timezone(self) -> None:
        """DoneCompletion.start_time rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="start_time must have timezone info"):
            DoneCompletion(
                assignee=WorkerId("w1"),
                hours_logged=1.0,
                start_time=naive_dt,
                end_time=datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
            )

    def test_done_completion_end_time_requires_timezone(self) -> None:
        """DoneCompletion.end_time rejects naive datetime."""
        naive_dt = datetime(2024, 1, 2, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="end_time must have timezone info"):
            DoneCompletion(
                assignee=WorkerId("w1"),
                hours_logged=1.0,
                start_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                end_time=naive_dt,
            )

    def test_dag_event_timestamp_requires_timezone(self) -> None:
        """DAGEvent.timestamp rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="timestamp must have timezone info"):
            DAGEvent(
                id=EventId("e1"),
                event_type=EventType.NODE_CREATED,
                timestamp=naive_dt,
                resulting_dag_version=DAGVersionId("v1"),
            )

    def test_task_event_timestamp_requires_timezone(self) -> None:
        """TaskEvent.timestamp rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="timestamp must have timezone info"):
            TaskEvent(
                node_id=TaskId("t1"),
                event_type="start",
                timestamp=naive_dt,
            )

    def test_checkpoint_timestamp_requires_timezone(self) -> None:
        """Checkpoint.timestamp rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="timestamp must have timezone info"):
            Checkpoint(
                timestamp=naive_dt,
                completed_samples=0,
            )

    def test_simulation_start_date_requires_timezone(self) -> None:
        """Simulation.start_date rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="start_date must have timezone info"):
            Simulation(
                id=SimulationId("sim1"),
                dag_version_id=DAGVersionId("v1"),
                status=SimulationStatus.RUNNING,
                start_date=naive_dt,
                num_samples=100,
                num_parallel_processes=1,
            )

    def test_project_metadata_created_requires_timezone(self) -> None:
        """ProjectMetadata.created rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="created must have timezone info"):
            ProjectMetadata(
                name="Test",
                created=naive_dt,
                last_modified=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            )

    def test_project_metadata_last_modified_requires_timezone(self) -> None:
        """ProjectMetadata.last_modified rejects naive datetime."""
        naive_dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="last_modified must have timezone info"):
            ProjectMetadata(
                name="Test",
                created=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                last_modified=naive_dt,
            )
