"""ID generation utilities for DAG nodes, versions, and events."""

import secrets
from datetime import UTC, datetime

from fluxx.data.models import (
    BranchId,
    DAGVersionId,
    EventId,
    PersistentObjectId,
    PossibleWorldId,
    TaskId,
)


def generate_task_id() -> TaskId:
    """Generate a unique task ID.

    Returns:
        A unique TaskId
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return TaskId(f"task_{timestamp}_{random_suffix}")


def generate_branch_id() -> BranchId:
    """Generate a unique branch ID.

    Returns:
        A unique BranchId
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return BranchId(f"branch_{timestamp}_{random_suffix}")


def generate_possible_world_id() -> PossibleWorldId:
    """Generate a unique possible world ID.

    Returns:
        A unique PossibleWorldId
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return PossibleWorldId(f"pw_{timestamp}_{random_suffix}")


def generate_persistent_object_id() -> PersistentObjectId:
    """Generate a unique persistent object ID.

    Returns:
        A unique PersistentObjectId
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return PersistentObjectId(f"pobj_{timestamp}_{random_suffix}")


def generate_dag_version_id() -> DAGVersionId:
    """Generate a unique DAG version ID.

    Returns:
        A unique DAGVersionId
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return DAGVersionId(f"v_{timestamp}_{random_suffix}")


def generate_event_id() -> EventId:
    """Generate a unique event ID.

    Returns:
        A unique EventId
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return EventId(f"event_{timestamp}_{random_suffix}")
