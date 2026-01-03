# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Fluxx is project planning software that incorporates uncertainty. It models projects as directed acyclic graphs (DAGs) with tasks and branches (decision points), supporting duration distributions and Monte Carlo simulation to generate probabilistic timelines and Gantt charts.

## Essential Commands

### Development Setup
```bash
# Install package in development mode with dev dependencies
make install
# Or manually: pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests with coverage
make test

# Show files with incomplete coverage
make coverage

# Run a single test file
QT_QPA_PLATFORM=offscreen pytest tests/test_models.py -v

# Run a single test function
QT_QPA_PLATFORM=offscreen pytest tests/test_models.py::test_function_name -v
```

**Important**: Always use `QT_QPA_PLATFORM=offscreen` when running pytest to prevent GUI crashes in sandboxed environments.

### Code Quality
```bash
# Run all checks (format, lint, type-check, test, coverage)
make all_checks

# Format code with ruff
make format

# Run ruff linter
make lint

# Run mypy type checker
make type-check
```

### Pre-commit Hooks
Pre-commit hooks automatically run ruff and mypy. Install with:
```bash
pre-commit install
```

## Architecture

### Core Module Structure

The codebase is organized into three main packages:

**`fluxx.data`** - Data models and persistence
- `models.py`: Pydantic models for all data structures (tasks, branches, workers, simulations)
- `validation.py`: DAG validation (cycle detection, dependency consistency)
- `dag_operations.py`: Operations for modifying the DAG
- `persistence.py`: JSON serialization/deserialization for `.fluxx` project files
- `undo.py`: History tracking and undo/redo system with branching history support
- `id_generation.py`: UUID-based ID generation for all entities

**`fluxx.simulation`** - Monte Carlo simulation engine
- `engine.py`: Main simulation loop, parallel execution, checkpointing
- `scheduler.py`: Task scheduling logic, worker assignment, dependency resolution
- `state.py`: Simulation state tracking (worker availability, task assignments, timeline events)
- `calendar.py`: Calendar-aware time tracking (work hours, weekends)
- `distributions.py`: Duration distribution implementations (ShiftedLognormal, Triangular)

**`fluxx.gui`** - PySide6-based user interface
- `main_window.py`: Main application window
- `controller.py`: Mediates between GUI and data/simulation layers
- `panels/`: DAG panel, editor panel, control bar
- `widgets/`: Reusable UI components (DAG view, node editors, list view)
- `simulation/`: Simulation dialogs and visualization widgets

**`fluxx.visualization`** - Chart generation
- `gantt.py`: Gantt chart generation using linear programming optimization (pyomo)

### Key Architectural Patterns

**Endpoint-Based Dependencies**: Dependencies connect specific endpoints (start/end for tasks, occurrence_point for branches, possible world IDs for branch outcomes). This enables precise temporal constraints and cycle detection in the dependency graph.

**Persistent Objects with Versioning**: Tasks and branches use persistent object IDs that remain valid even after deletion. Each modification creates a new version. Simulations reference specific DAG versions, ensuring reproducibility when nodes are modified or deleted.

**History Tree**: The undo system maintains a tree (not just a linear stack). Undoing and making a different change creates a branch. All branches are preserved and navigable.

**Type-Safe IDs**: Uses NewType for semantic ID types (`TaskId`, `BranchId`, `WorkerId`, etc.) to prevent mixing different ID types at the type checker level.

**Union Type Discrimination**: `NodeId = TaskId | BranchId` and `DependencyTargetId = NodeId | PossibleWorldReference`. Use pattern matching or `type_explode_id()` to discriminate.

**Complete Result Storage**: Simulations store complete sampling results (all events, timestamps, outcomes), not just RNG seeds. This ensures visualizations remain unchanged even if simulation code is modified.

## Code Quality Requirements

- **100% test coverage** required (enforced via pytest-cov)
- **Full type annotations** required (enforced via mypy --strict)
- **Pydantic validation** for all data schemas
- **Pre-commit hooks** must pass before commits

See also:
- **[testing.md](testing.md)** - Detailed testing patterns, mocking strategies, and common pitfalls
- **[type_safety.md](type_safety.md)** - Type system guidelines, ID types, and avoiding `Any`/`cast`

## Testing Guidelines

### GUI Testing
GUI components are tested using `pytest-qt`. Key patterns:

```python
def test_widget_interaction(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)

    # Simulate user interactions
    qtbot.mouseClick(widget.button, Qt.LeftButton)

    # Assert state changes
    assert widget.some_state == expected_value
```

### Simulation Testing
Simulations use deterministic RNG seeding for reproducibility:

```python
def test_simulation():
    # Create simulation with fixed seed for reproducibility
    sim = Simulation(...)
    results = sim.run(seed=42)

    # Verify deterministic behavior
    assert results.samples[0].events == expected_events
```

## Domain-Specific Concepts

**Possible Worlds**: Branch nodes represent uncertain decisions (e.g., "Which database will we use?"). Each branch has multiple possible worlds (outcomes) with probabilities. Tasks can depend on specific possible worlds, meaning they only execute in samples where that world was chosen.

**Worker Constraints**: Tasks can specify allowed workers or exclude workers assigned to other tasks (useful for "different developers must review each other's code" scenarios).

**Shifted Lognormal Distribution**: A lognormal distribution with its minimum shifted from 0 to a specified value. Used for task duration modeling because it captures realistic right-skewed uncertainty (tasks can take much longer than expected, but have a hard minimum).

**Duration Distributions**: Leaf tasks (tasks with no children) must have duration distributions. Parent task durations are implicitly determined by their subtasks. All durations measured in work-hours.

**Percentile-Based Gantt Charts**: Uses linear programming to find the tightest timeline where all task start times and durations are at or above the specified percentile (e.g., 97th), while respecting dependencies.

## Important File Locations

- **Project specification**: `project_fluxx_specification.md` - comprehensive technical specification (refer to this for design decisions)
- **Main entry point**: `src/fluxx/__main__.py`
- **Data models**: `src/fluxx/data/models.py`
- **Test files**: `tests/` (organized by module)

## Running the Application

```bash
# Run the GUI application
python -m fluxx

# Or if installed:
fluxx
```

## Common Pitfalls

1. **ID Type Confusion**: Use the typed ID newtypes consistently. Don't pass a string where a `TaskId` is expected without explicitly converting. See [type_safety.md](type_safety.md) for details.

2. **Qt Environment**: Always set `QT_QPA_PLATFORM=offscreen` for tests. GUI tests will crash in sandboxed environments without this. See [testing.md](testing.md) for mocking patterns.

3. **Dependency Cycles**: When adding dependencies, always validate for cycles. The dependency graph must be acyclic. The cycles are accounted with the endpoints (e.g, start, end, possible world).

4. **Parent/Child Constraints**: When creating subtasks, parent-child temporal constraints (child.start >= parent.start, parent.end >= child.end) are added automatically by the system.

5. **Simulation Reproducibility**: Never modify stored simulation results. If the simulation algorithm changes, historical simulations must remain unchanged (they store complete results, not just seeds).

6. **Never use `Any` or `cast`**: The type system in this codebase is designed to be complete. If you think you need `Any` or `cast`, you're likely misunderstanding the types. See [type_safety.md](type_safety.md).
