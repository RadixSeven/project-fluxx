"""Pydantic data models for Project Fluxx.

Based on the specification in project_fluxx_specification.md section 3.
"""

import re
from abc import ABC
from datetime import datetime
from enum import Enum
from typing import Any, NewType

from pydantic import BaseModel, Field, field_validator, model_validator

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

# Union types for nodes and dependency targets
NodeId = (
    TaskId | BranchId
)  # Nodes that exist in the DAG (use get_node_id_type to distinguish)
PossibleWorldReference = NewType(
    "PossibleWorldReference", str
)  # Format: "branch_id:world_id"
DependencyTargetId = (
    NodeId | PossibleWorldReference
)  # Things that can be dependency targets (use get_node_id_type to distinguish)


class NodeIdType(str, Enum):
    """Type of node ID for pattern-based type discrimination."""

    TASK = "task"
    BRANCH = "branch"
    POSSIBLE_WORLD_REFERENCE = "possible_world_reference"


def get_node_id_type(node_id: str) -> NodeIdType:
    """Determine the type of a node ID based on its pattern.

    Args:
        node_id: The node ID string to check

    Returns:
        The type of the node ID

    Raises:
        ValueError: If the ID doesn't match any known pattern
    """
    # Check for possible world reference (contains colon)
    if ":" in node_id:
        return NodeIdType.POSSIBLE_WORLD_REFERENCE

    # Check for task ID patterns (production and test)
    if re.match(r"^task_\d+_[0-9a-f]+$", node_id) or re.match(r"^t\d+$", node_id):
        return NodeIdType.TASK

    # Check for branch ID patterns (production and test)
    if re.match(r"^branch_\d+_[0-9a-f]+$", node_id) or re.match(r"^b\d+$", node_id):
        return NodeIdType.BRANCH

    raise ValueError(f"Unknown node ID pattern: {node_id}")


def str_to_node_id(node_id_str: str) -> NodeId:
    """Convert a string to a properly-typed NodeId.

    Args:
        node_id_str: The node ID string

    Returns:
        TaskId or BranchId based on the pattern

    Raises:
        ValueError: If the ID doesn't match any known node pattern
    """
    node_type = get_node_id_type(node_id_str)

    if node_type == NodeIdType.TASK:
        return TaskId(node_id_str)
    elif node_type == NodeIdType.BRANCH:
        return BranchId(node_id_str)
    else:
        raise ValueError(
            f"Cannot convert '{node_id_str}' to NodeId: "
            f"it's a {node_type}, not a task or branch"
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
        if self.mode <= self.min:
            raise ValueError("mode must be greater than min")
        if self.percentile_95 <= self.min:
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


class Worker(BaseModel):
    """Worker in the project."""

    id: WorkerId = Field(description="Unique identifier")
    name: str = Field(description="Worker name")
    worker_id: str | None = Field(
        default=None, description="Optional ID for distinguishing same-named workers"
    )
    description: str | None = Field(default=None, description="Worker description")
    hours_per_workday: float = Field(description="Hours worker completes per workday")


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
    duration_distribution: Triangular | ShiftedLognormal | None = Field(
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
    actual_start_time: str | None = Field(
        default=None, description="When task actually started (ISO format)"
    )
    actual_assignee: WorkerId | None = Field(
        default=None, description="Worker ID who was actually assigned"
    )
    actual_duration: float | None = Field(
        default=None,
        description="Actual duration taken in work-hours. If set, task is done",
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


class TaskEvent(BaseModel):
    """Event during simulation (task start/end or branch resolution)."""

    timestamp: datetime = Field(description="When the event occurred")
    node_id: NodeId = Field(description="Task or branch ID")
    event_type: str = Field(description="Type of event (start, end, resolve)")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific details"
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

    version: str = Field(default="1.0", description="File format version")
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
