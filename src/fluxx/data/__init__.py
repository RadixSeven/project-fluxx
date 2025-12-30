"""Data models and schemas for Project Fluxx."""

from fluxx.data.dag_operations import (
    DAGOperationError,
    add_branch,
    add_dependency,
    add_task,
    remove_dependency,
    update_branch,
    update_task,
)
from fluxx.data.id_generation import (
    generate_branch_id,
    generate_dag_version_id,
    generate_event_id,
    generate_persistent_object_id,
    generate_task_id,
)
from fluxx.data.persistence import (
    FileFormatError,
    PersistenceError,
    VersionError,
    load_project,
    save_project,
)
from fluxx.data.undo import (
    UndoError,
    can_redo,
    can_undo,
    redo,
    undo,
)
from fluxx.data.validation import (
    CycleError,
    EndpointError,
    HierarchyError,
    ValidationError,
    WorkerConstraintError,
    validate_dag,
    validate_dependency,
)

__all__ = [
    # Persistence
    "save_project",
    "load_project",
    "PersistenceError",
    "FileFormatError",
    "VersionError",
    # Validation
    "validate_dag",
    "validate_dependency",
    "ValidationError",
    "CycleError",
    "EndpointError",
    "HierarchyError",
    "WorkerConstraintError",
    # DAG Operations
    "add_task",
    "add_branch",
    "add_dependency",
    "update_task",
    "update_branch",
    "remove_dependency",
    "DAGOperationError",
    # Undo/Redo
    "undo",
    "redo",
    "can_undo",
    "can_redo",
    "UndoError",
    # ID Generation
    "generate_task_id",
    "generate_branch_id",
    "generate_persistent_object_id",
    "generate_dag_version_id",
    "generate_event_id",
]
