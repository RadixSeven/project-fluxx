"""Pydantic data models for Project Fluxx.

Based on the specification in project_fluxx_specification.md section 3.
"""

from abc import ABC

from pydantic import BaseModel, Field, model_validator


class DurationDistribution(BaseModel, ABC):
    """Base class for all duration distributions."""

    pass


class ShiftedLognormal(DurationDistribution):
    """Shifted lognormal distribution.

    A lognormal distribution with minimum shifted from 0 to a specified value.
    """

    min: float = Field(description="Minimum duration")
    mode: float = Field(description="Most likely duration")
    percentile_95: float = Field(description="95th percentile duration")

    @model_validator(mode="after")
    def validate_parameters(self) -> "ShiftedLognormal":
        """Validate that mode and percentile_95 are greater than min."""
        if self.mode <= self.min:
            raise ValueError("mode must be greater than min")
        if self.percentile_95 <= self.min:
            raise ValueError("percentile_95 must be greater than min")
        return self


class Triangular(DurationDistribution):
    """Triangular distribution."""

    min: float = Field(description="Minimum duration")
    mode: float = Field(description="Most likely duration")
    max: float = Field(description="Maximum duration")

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

    id: str = Field(description="Unique identifier")
    name: str = Field(description="Worker name")
    worker_id: str | None = Field(
        default=None, description="Optional ID for distinguishing same-named workers"
    )
    description: str | None = Field(default=None, description="Worker description")
    hours_per_workday: float = Field(description="Hours worker completes per workday")


class Task(BaseModel):
    """Task node in the project DAG."""

    id: str = Field(description="Unique identifier")
    title: str = Field(description="Task title")
    description: str = Field(description="Task description")
    node_type: str = Field(default="task", description="Node type identifier")

    # Hierarchy
    parent_id: str | None = Field(
        default=None, description="Parent task ID if this is a subtask"
    )
    children: list[str] = Field(
        default_factory=list, description="List of child task IDs"
    )

    # Duration distribution (for leaf tasks only)
    duration_distribution: DurationDistribution | None = Field(
        default=None, description="Duration distribution for leaf tasks"
    )

    # Worker constraints
    allowed_workers: list[str] | None = Field(
        default=None,
        description="Whitelist of worker IDs. If None, all workers are allowed",
    )
    excluded_worker_tasks: list[str] = Field(
        default_factory=list,
        description="Task IDs whose assignees cannot be assigned to this task",
    )

    # Completion tracking
    actual_start_time: str | None = Field(
        default=None, description="When task actually started (ISO format)"
    )
    actual_assignee: str | None = Field(
        default=None, description="Worker ID who was actually assigned"
    )
    actual_duration: float | None = Field(
        default=None, description="Actual duration taken. If set, task is done"
    )


class Branch(BaseModel):
    """Branch node representing uncertain conditions/events."""

    id: str = Field(description="Unique identifier")
    title: str = Field(description="Branch title")
    description: str = Field(description="Branch description")
    node_type: str = Field(default="branch", description="Node type identifier")

    # Completion tracking
    chosen_world_id: str | None = Field(
        default=None,
        description="ID of the chosen possible world. If set, branch is resolved",
    )
