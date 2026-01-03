# Type Safety Guidelines for LLMs

This document provides guidance for LLMs writing type-safe code in this codebase.

## Core Principles

1. **Never use `Any`** unless absolutely necessary (and document why)
2. **Never use `cast`** unless the type system cannot express the constraint
3. **Never use `# type: ignore`** without a specific error code and justification
4. **Respect the mathematical structure of types** - the type checker prevents bugs

## Typed ID System

This codebase uses NewType for semantic ID types to prevent mixing different ID types:

```python
from fluxx.data.models import (
    TaskId,
    BranchId,
    NodeId,          # TaskId | BranchId
    PossibleWorldId,
    PersistentObjectId,
    DAGVersionId,
)

# Correct
task_id = TaskId("t1")
branch_id = BranchId("b1")

# Wrong - don't use raw strings where typed IDs are expected
task_id = "t1"  # Type error
```

## Union Type Discrimination

`NodeId = TaskId | BranchId` and `DependencyTargetId = NodeId | PossibleWorldReference` are union types. Use pattern matching or the provided helper functions:

```python
from fluxx.data.models import type_explode_id, extract_node_id, get_dep_id_type

# Discriminate a DependencyTargetId
def handle_target(target_id: DependencyTargetId) -> None:
    as_task, as_branch, as_world = type_explode_id(target_id)

    if as_task is not None:
        # Handle TaskId
        process_task(as_task)
    elif as_branch is not None:
        # Handle BranchId
        process_branch(as_branch)
    elif as_world is not None:
        # Handle PossibleWorldReferencePair (branch_id, world_id)
        branch_id, world_id = as_world
        process_world(branch_id, world_id)
```

## Pydantic Models

All data structures use Pydantic with strict validation:

```python
from fluxx.data.models import PossibleWorld, PossibleWorldId

# Correct - use proper field names and types
pw = PossibleWorld(
    id=PossibleWorldId("pw1"),
    title="World 1",
    weight=0.5,  # Not "probability"
)

# Wrong - will fail at runtime and type-check time
pw = PossibleWorld(id="pw1", title="World 1", probability=0.5)
```

Check model definitions in `src/fluxx/data/models.py` for correct field names.

## Function Signatures

Always provide complete type annotations:

```python
# Correct
def process_nodes(
    project: Project,
    node_ids: list[NodeId],
) -> dict[NodeId, QPointF]:
    ...

# Wrong - missing annotations
def process_nodes(project, node_ids):
    ...
```

## Generic Collections

Use generic types for collections:

```python
# Correct
positions: dict[NodeId, QPointF] = {}
node_list: list[TaskId] = []
endpoint_set: set[tuple[NodeId, Endpoint]] = set()

# Wrong - untyped collections
positions = {}
node_list = []
```

## Optional and None Handling

Be explicit about optionality:

```python
def get_task(task_id: TaskId) -> Task | None:
    ...

# When using the result, handle None explicitly
task = get_task(task_id)
if task is None:
    return  # Early return for None case
# Now task is narrowed to Task
process(task)
```

## Common Type Errors and Fixes

### Wrong ID Type

```python
# Error: Argument "id" has incompatible type "str"; expected "PossibleWorldId"
pw = PossibleWorld(id="pw1", ...)

# Fix: Use the typed ID
pw = PossibleWorld(id=PossibleWorldId("pw1"), ...)
```

### Missing Field or Wrong Field Name

```python
# Error: Unexpected keyword argument "probability" for "PossibleWorld"
pw = PossibleWorld(..., probability=0.5)

# Fix: Check the model definition for correct field names
pw = PossibleWorld(..., weight=0.5)
```

### Incompatible Return Type

```python
# Error: Incompatible return value type (got "str", expected "TaskId")
def get_id() -> TaskId:
    return "t1"  # Wrong

# Fix: Return the correct type
def get_id() -> TaskId:
    return TaskId("t1")
```

## Refactoring for Type Safety

When refactoring, prefer extracting functions over using type assertions:

```python
# Instead of complex type narrowing inline, extract a helper:
def _build_dependency_graph(project: Project) -> dict[...]:
    """Build graph with clear input/output types."""
    graph: dict[tuple[NodeId, Endpoint], list[tuple[NodeId, Endpoint]]] = {}
    # ... build graph ...
    return graph

def _detect_cycles(graph: dict[...]) -> None:
    """Detect cycles - pure function with clear types."""
    # ... cycle detection ...
```

## Validation

Always run type checking before committing:

```bash
source venv/bin/activate && mypy --strict src/fluxx tests
```

Or use the full check suite:

```bash
source venv/bin/activate && make all_checks
```
