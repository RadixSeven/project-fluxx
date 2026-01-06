"""Pydantic data models for Project Fluxx.

Based on the specification in project_fluxx_specification.md section 3.
"""

import re
from abc import ABC
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, NamedTuple, NewType, TypedDict, cast

from pydantic import (
    BaseModel,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)

from fluxx.data.json_types import JsonObject
from fluxx.jira.models import JiraConfig, JiraReference

# Type definitions for IDs to provide semantic meaning


TaskId = NewType("TaskId", str)
BranchId = NewType("BranchId", str)
WorkerId = NewType("WorkerId", str)
PossibleWorldId = NewType("PossibleWorldId", str)
DAGId = NewType("DAGId", str)
DAGVersionId = NewType("DAGVersionId", str)
EventId = NewType("EventId", str)
SimulationId = NewType("SimulationId", str)
PersistentObjectId = NewType("PersistentObjectId", str)
SampleId = NewType("SampleId", int)

###
# Union types for nodes and dependency targets
###

# Nodes that exist in the DAG (use get_node_id_type to distinguish)
NodeId = TaskId | BranchId

PossibleWorldReference = NewType(
    "PossibleWorldReference", str
)  # Format: "branch_id:world_id"

# Things that can be dependency targets (use get_node_id_type to distinguish)
DependencyTargetId = NodeId | PossibleWorldReference


class PossibleWorldReferencePair(NamedTuple):
    branch_id: BranchId
    world_id: PossibleWorldId


def split_world_reference(ref: PossibleWorldReference) -> PossibleWorldReferencePair:
    """
    Split a possible world reference into its branch and world ID components.

    Args:
        ref: The possible world reference string

    Returns:
        A tuple containing the branch ID and world ID

    Raises:
        ValueError: If the reference does not match the expected format
    """
    branch_id_str, world_id_str = ref.split(":", 1)
    return PossibleWorldReferencePair(
        branch_id=BranchId(branch_id_str),
        world_id=PossibleWorldId(world_id_str),
    )


class DependencyTargetIdType(str, Enum):
    """Type of dependency target ID for pattern-based type discrimination."""

    TASK = "task"
    BRANCH = "branch"
    POSSIBLE_WORLD_REFERENCE = "possible_world_reference"


def type_explode_id(
    ref: DependencyTargetId,
) -> tuple[TaskId | None, BranchId | None, PossibleWorldReferencePair | None]:
    """Return a tuple of the possible IDs ``ref`` could be. Exactly one will
    not be None, the one with the correct type. (This throws if the ID
    doesn't match any known pattern)

    Args:
        ref: The dependency target ID to type-explode

    Returns:
        A tuple of the possible IDs that ``ref`` could be, with exactly
        one element not being None -- the one with the correct type.

    Raises:
        ValueError: If the ID doesn't match any known pattern
    """
    # The casts are OK in this function because its purpose is
    # validating and propagating the type information

    # Check for possible world reference (contains colon)
    if ":" in ref:
        return None, None, split_world_reference(cast(PossibleWorldReference, ref))

    # Check for task ID patterns (production and test)
    if re.match(r"^task_\d+_[0-9a-f]+$", ref) or re.match(r"^t\d*(?:_[.\w]+)?$", ref):
        return cast(TaskId, ref), None, None

    # Check for branch ID patterns (production and test)
    if re.match(r"^branch_\d+_[0-9a-f]+$", ref) or re.match(r"^b\d*(?:_[.\w]+)?$", ref):
        return None, cast(BranchId, ref), None

    raise ValueError(f"Unknown dependency target ID pattern: {ref}")


def extract_node_id(id_: DependencyTargetId) -> NodeId:
    """Extract the DAG node id from dependency target ID by using the branch part
    of a possible world reference."""
    as_task, as_branch, as_world = type_explode_id(id_)
    if as_task is not None:
        return as_task
    if as_branch is not None:
        return as_branch
    if as_world is not None:
        return as_world.branch_id
    raise ValueError(f"Forgot to add branch to force_node_id for id type of {id_}")


def get_dep_id_type(id_: DependencyTargetId) -> DependencyTargetIdType:
    """Determine the type of an ID based on its pattern.

    Args:
        id_: The dependency target ID string to check

    Returns:
        The type of the node ID

    Raises:
        ValueError: If the ID doesn't match any known pattern
    """
    # This will throw - so we know exactly one is not None
    t, b, w = type_explode_id(id_)
    if t is not None:
        return DependencyTargetIdType.TASK
    if b is not None:
        return DependencyTargetIdType.BRANCH
    return DependencyTargetIdType.POSSIBLE_WORLD_REFERENCE


def str_to_node_id(node_id_str: str) -> NodeId:
    """Convert a string to a properly typed NodeId.

    Args:
        node_id_str: The node ID string

    Returns:
        TaskId or BranchId based on the pattern

    Raises:
        ValueError: If the ID doesn't match any known node pattern
    """
    # This cast is OK because this function is a utility to
    # safely avoid other casts.
    as_task, as_branch, _ = type_explode_id(cast(NodeId, node_id_str))

    if as_task is not None:
        return as_task
    elif as_branch is not None:
        return as_branch
    raise ValueError(
        f"Cannot convert '{node_id_str}' to NodeId: it's not a task or branch ID"
    )


class DurationDistribution(BaseModel, ABC):
    """Base class for all duration distributions."""

    pass


class ShiftedLognormal(DurationDistribution):
    """Shifted lognormal distribution.

    A lognormal distribution with minimum shifted from 0 to a specified value.
    All durations are measured in work-hours.
    """

    min: float = Field(description="Minimum duration (work-hours)")
    mode: float = Field(description="Most likely duration (work-hours)")
    percentile_95: float = Field(description="95th percentile duration (work-hours)")

    @model_validator(mode="after")
    def validate_parameters(self) -> "ShiftedLognormal":
        """Validate that mode and percentile_95 are greater than min."""
        if self.mode < self.min:
            raise ValueError("mode must be greater than min")
        if self.percentile_95 < self.min:
            raise ValueError("percentile_95 must be greater than min")
        return self


class Triangular(DurationDistribution):
    """Triangular distribution.

    All durations are measured in work-hours.
    """

    min: float = Field(description="Minimum duration (work-hours)")
    mode: float = Field(description="Most likely duration (work-hours)")
    max: float = Field(description="Maximum duration (work-hours)")

    @model_validator(mode="after")
    def validate_parameters(self) -> "Triangular":
        """Validate that mode > min and max > mode."""
        if self.mode <= self.min:
            raise ValueError("mode must be greater than min")
        if self.max <= self.mode:
            raise ValueError("max must be greater than mode")
        return self


class JiraDurationDistribution(DurationDistribution):
    """Duration distribution for Jira-imported tasks.

    Stores Jira-specific parameters that are used to condition the sampling
    from a bin-based distribution model. The actual sampling is deferred to
    the simulation engine which uses a BinBasedDistributionModel.

    All fields are optional since Jira data may not include these values.
    """

    original_estimate_seconds: int | None = Field(
        default=None,
        description="Original estimate from Jira in seconds",
    )
    story_points: float | None = Field(
        default=None,
        description="Story points assigned to the issue",
    )
    remaining_estimate_seconds: int | None = Field(
        default=None,
        description="Remaining estimate from Jira in seconds",
    )


class Worker(BaseModel):
    """Worker in the project."""

    id: WorkerId = Field(description="Unique identifier")
    name: str = Field(description="Worker name")
    worker_id: str | None = Field(
        default=None, description="Optional ID for distinguishing same-named workers"
    )
    description: str | None = Field(default=None, description="Worker description")
    hours_per_workday: float = Field(description="Hours worker completes per workday")

    # Jira integration
    jira_account_id: str | None = Field(
        default=None,
        description="Jira account ID for mapping worklogs to this worker",
    )


# Enums and supporting classes


class ConstraintType(str, Enum):
    """Type of dependency constraint."""

    GREATER_EQUAL = ">="
    EQUAL = "="


class Endpoint(str, Enum):
    """Endpoint of a task or branch."""

    START = "start"
    END = "end"
    OCCURRENCE = "occurrence_point"


class Dependency(BaseModel):
    """Dependency between task/branch endpoints.

    Semantics:
        containing_node[source_endpoint]
           <constraint>
        target_node[target_endpoint]

    Example:
    # Add dependency: task1.end >= task2.start
    Dependency(
        source_endpoint=Endpoint.END,
        target_node_id=task2_id,
        target_endpoint=Endpoint.START,
        constraint_type=ConstraintType.GREATER_EQUAL,
    )
    """

    source_endpoint: Endpoint = Field(description="Source endpoint type")
    target_node_id: DependencyTargetId = Field(
        description="Target: TaskId, BranchId, or PossibleWorldReference"
    )
    target_endpoint: Endpoint = Field(description="Target endpoint type")
    constraint_type: ConstraintType = Field(description="Type of constraint")


class PossibleWorld(BaseModel):
    """One possible outcome of a branch node."""

    id: PossibleWorldId = Field(description="Unique identifier")
    title: str = Field(description="Possible world title")
    description: str = Field(default="", description="Possible world description")
    weight: float = Field(default=1.0, description="Weight for probability calculation")

    @field_validator("weight")
    @classmethod
    def weight_must_be_positive(cls, v: float) -> float:
        """Validate that weight is positive."""
        if v <= 0:
            raise ValueError("weight must be positive")
        return v


# Task Completion Models


class NotStartedCompletion(BaseModel):
    """Task has not been started."""

    status: Literal["not_started"] = Field(
        default="not_started",
        description="Completion status discriminator",
    )


class StartedCompletion(BaseModel):
    """Task is in progress."""

    status: Literal["started"] = Field(
        default="started",
        description="Completion status discriminator",
    )
    assignee: WorkerId = Field(description="Worker assigned to this task")
    start_time: datetime = Field(description="When work began (for Gantt charts)")
    hours_logged: float = Field(
        default=0.0, description="Work-hours spent so far on this task"
    )

    @field_validator("hours_logged")
    @classmethod
    def hours_logged_non_negative(cls, v: float) -> float:
        """Validate that hours_logged is non-negative."""
        if v < 0:
            raise ValueError("hours_logged must be non-negative")
        return v


class DoneCompletion(BaseModel):
    """Task is completed."""

    status: Literal["done"] = Field(
        default="done",
        description="Completion status discriminator",
    )
    assignee: WorkerId = Field(description="Worker who completed this task")
    start_time: datetime = Field(description="When work began")
    hours_logged: float = Field(description="Total work-hours spent on this task")
    end_time: datetime = Field(description="When work finished (for Gantt charts)")

    @field_validator("hours_logged")
    @classmethod
    def hours_logged_positive(cls, v: float) -> float:
        """Validate that hours_logged is positive for completed tasks."""
        if v <= 0:
            raise ValueError("hours_logged must be positive for completed tasks")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "DoneCompletion":
        """Validate that end_time is after start_time."""
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


def _get_completion_discriminator(
    v: JsonObject | NotStartedCompletion | StartedCompletion | DoneCompletion,
) -> str:
    """Get discriminator value for TaskCompletion union."""
    if isinstance(v, dict):
        status = v.get("status", "not_started")
        return str(status) if status is not None else "not_started"
    return v.status


# Union type for task completion - discriminated by 'status' field
TaskCompletion = Annotated[
    Annotated[NotStartedCompletion, Tag("not_started")]
    | Annotated[StartedCompletion, Tag("started")]
    | Annotated[DoneCompletion, Tag("done")],
    Discriminator(_get_completion_discriminator),
]


# Node models


class Task(BaseModel):
    """Task node in the project DAG."""

    id: TaskId = Field(description="Unique identifier")
    title: str = Field(description="Task title")
    description: str = Field(description="Task description")
    node_type: str = Field(default="task", description="Node type identifier")

    # Hierarchy
    parent_id: TaskId | None = Field(
        default=None, description="Parent task ID if this is a subtask"
    )
    children: list[TaskId] = Field(
        default_factory=list, description="List of child task IDs"
    )

    # Duration distribution (for leaf tasks only)
    duration_distribution: (
        Triangular | ShiftedLognormal | JiraDurationDistribution | None
    ) = Field(
        default=None,
        description="Duration distribution for leaf tasks (work-hours)",
    )

    # Dependencies
    dependencies: list[Dependency] = Field(
        default_factory=list, description="Dependencies for this task"
    )

    # Worker constraints
    allowed_workers: list[WorkerId] | None = Field(
        default=None,
        description=(
            "Whitelist of worker IDs. If None, all workers are allowed. "
            "Empty lists are automatically normalized to None. "
            "Use get_allowed_worker_ids() method to access this field safely."
        ),
    )
    excluded_worker_tasks: list[TaskId] = Field(
        default_factory=list,
        description="Task IDs whose assignees cannot be assigned to this task",
    )

    @field_validator("allowed_workers")
    @classmethod
    def normalize_allowed_workers(
        cls, v: list[WorkerId] | None
    ) -> list[WorkerId] | None:
        """Normalize empty list to None for consistent semantics.

        Both None and empty list mean "all workers allowed", but we normalize
        to None for uniform internal representation.
        """
        if v is not None and len(v) == 0:
            return None
        return v

    # Completion tracking
    completion: TaskCompletion = Field(
        default_factory=NotStartedCompletion,
        description="Task completion state",
    )

    # Jira integration
    jira_reference: JiraReference | None = Field(
        default=None,
        description="Reference to linked Jira issue (server URL + issue key)",
    )
    jira_issue_type: str | None = Field(
        default=None,
        description="Jira issue type (e.g., 'Epic', 'Story', 'Bug', 'Task')",
    )

    def get_allowed_worker_ids(self, all_workers: list[WorkerId]) -> list[WorkerId]:
        """Get the list of workers allowed to work on this task.

        Args:
            all_workers: Complete list of available worker IDs

        Returns:
            List of worker IDs allowed for this task.
            Returns all_workers if no restriction, or the whitelist if restricted.
        """
        # None means "all workers allowed" (empty lists are normalized to None)
        if self.allowed_workers is None:
            return all_workers

        # Otherwise return the restricted whitelist
        return self.allowed_workers


class Branch(BaseModel):
    """Branch node representing uncertain conditions/events."""

    id: BranchId = Field(description="Unique identifier")
    title: str = Field(description="Branch title")
    description: str = Field(description="Branch description")
    node_type: str = Field(default="branch", description="Node type identifier")

    # Possible worlds
    possible_worlds: list[PossibleWorld] = Field(
        default_factory=list, description="List of possible outcomes"
    )

    # Dependencies (on occurrence point)
    dependencies: list[Dependency] = Field(
        default_factory=list, description="Dependencies for occurrence point"
    )

    # Completion tracking
    chosen_world_id: PossibleWorldId | None = Field(
        default=None,
        description="ID of the chosen possible world. If set, branch is resolved",
    )


# DAG and History Models


class DAG(BaseModel):
    """Directed Acyclic Graph representing the project structure."""

    id: DAGId = Field(description="Unique identifier")
    current_version_id: DAGVersionId = Field(description="Current DAG version ID")
    node_map: dict[NodeId, PersistentObjectId] = Field(
        default_factory=dict,
        description="Maps node IDs to persistent object IDs",
    )


class EventType(str, Enum):
    """Type of history event."""

    NODE_CREATED = "node_created"
    NODE_MODIFIED = "node_modified"
    NODE_DELETED = "node_deleted"
    SIMULATION_CREATED = "simulation_created"
    SIMULATION_COMPLETED = "simulation_completed"


class DAGEvent(BaseModel):
    """Event in the project history."""

    id: EventId = Field(description="Unique identifier")
    timestamp: datetime = Field(description="When the event occurred")
    parent_event_id: EventId | None = Field(
        default=None, description="Parent event in history tree"
    )
    event_type: EventType = Field(description="Type of event")
    affected_nodes: list[NodeId] = Field(
        default_factory=list, description="Node IDs affected by this event"
    )
    resulting_dag_version: DAGVersionId = Field(
        description="DAG version ID after this event"
    )


class PersistentTask(BaseModel):
    """Persistent storage for task with all versions."""

    id: PersistentObjectId = Field(description="Unique identifier (never reused)")
    versions: dict[DAGVersionId, Task] = Field(
        default_factory=dict, description="Map of version ID to Task snapshot"
    )


class PersistentBranch(BaseModel):
    """Persistent storage for branch with all versions."""

    id: PersistentObjectId = Field(description="Unique identifier (never reused)")
    versions: dict[DAGVersionId, Branch] = Field(
        default_factory=dict, description="Map of version ID to Branch snapshot"
    )


# Simulation Models


class SimulationStatus(str, Enum):
    """Status of a simulation."""

    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class TaskEventDetails(TypedDict, total=False):
    """Type definition for event-specific details.

    Different event types use different fields:
    - start: worker_id, estimated_duration, estimated_completion
    - complete: worker_id
    - branch_resolved: chosen_world
    """

    worker_id: str | None
    estimated_duration: float
    estimated_completion: str
    chosen_world: str


# Valid event types for simulation events
TaskEventType = Literal["start", "complete", "branch_resolved"]


class TaskEvent(BaseModel):
    """Event during simulation (task start/end or branch resolution)."""

    timestamp: datetime = Field(description="When the event occurred")
    node_id: NodeId = Field(description="Task or branch ID")
    event_type: TaskEventType = Field(description="Type of event")
    details: TaskEventDetails = Field(
        default_factory=lambda: TaskEventDetails(),
        description="Event-specific details",
    )


class Sample(BaseModel):
    """Single simulation run sample."""

    sample_id: SampleId = Field(description="Sample identifier")
    events: list[TaskEvent] = Field(
        default_factory=list, description="All events in this sample"
    )
    failed_tasks: list[TaskId] = Field(
        default_factory=list,
        description="Task IDs that couldn't be completed (empty if successful)",
    )


class Checkpoint(BaseModel):
    """Checkpoint for resuming interrupted simulations."""

    timestamp: datetime = Field(description="When checkpoint was created")
    completed_samples: int = Field(description="Number of samples completed")
    rng_state: list[Any] = Field(
        default_factory=list, description="RNG states for each parallel process"
    )


class Simulation(BaseModel):
    """Monte Carlo simulation of project timeline."""

    id: SimulationId = Field(description="Unique identifier")
    dag_version_id: DAGVersionId = Field(
        description="DAG version ID when simulation was created"
    )
    start_date: datetime = Field(description="Project start date for simulation")
    num_samples: int = Field(description="Target number of samples")
    num_parallel_processes: int = Field(
        description="Number of parallel simulation processes"
    )

    # Status
    status: SimulationStatus = Field(description="Current simulation status")
    completed_samples: int = Field(
        default=0, description="Number of samples completed so far"
    )

    # Results
    samples: list[Sample] = Field(
        default_factory=list, description="All completed samples"
    )

    # Checkpoint
    last_checkpoint: Checkpoint | None = Field(
        default=None, description="Last checkpoint for resuming"
    )


# Project Container Models


class ProjectMetadata(BaseModel):
    """Metadata for a project."""

    name: str = Field(description="Project name")
    created: datetime = Field(description="When project was created")
    last_modified: datetime = Field(description="When project was last modified")


class Project(BaseModel):
    """Top-level project container."""

    version: str = Field(default="1.2", description="File format version")
    metadata: ProjectMetadata = Field(description="Project metadata")

    # Core data
    workers: list[Worker] = Field(
        default_factory=list, description="All workers in the project"
    )
    dag: DAG = Field(description="Current DAG structure")

    # Persistent objects
    persistent_tasks: dict[PersistentObjectId, PersistentTask] = Field(
        default_factory=dict, description="All task versions"
    )
    persistent_branches: dict[PersistentObjectId, PersistentBranch] = Field(
        default_factory=dict, description="All branch versions"
    )

    # History
    history_events: list[DAGEvent] = Field(
        default_factory=list, description="All history events"
    )
    current_event_id: EventId | None = Field(
        default=None, description="Current position in history"
    )

    # Simulations
    simulations: list[Simulation] = Field(
        default_factory=list, description="All simulations for this project"
    )

    # Jira integration
    jira_config: JiraConfig | None = Field(
        default=None, description="Jira integration configuration"
    )
