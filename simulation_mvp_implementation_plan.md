# Project Fluxx Simulation Engine Implementation Plan

## Overview
Implement the simulation engine for Project Fluxx to run Monte Carlo simulations of project timelines. **Scope**: Sequential single-sample simulation with design that can be parallelized later. No parallel execution or checkpointing in this iteration.

## Architecture

### Module Structure
```
src/fluxx/simulation/
├── __init__.py                 # Exports SimulationEngine
├── engine.py                   # Main engine (orchestrator)
├── distributions.py (NEW)      # Distribution sampling
├── calendar.py (NEW)           # Calendar/work-time utilities
├── scheduler.py (NEW)          # Task scheduling logic
└── state.py (NEW)              # Simulation state management
```

### Module Responsibilities

**distributions.py**: Convert distribution models to numpy samples
- `sample_shifted_lognormal(dist, rng) -> float`
- `sample_triangular(dist, rng) -> float`
- `sample_with_rejection(dist, rng, min_value) -> float` (for in-progress tasks)
- Includes exponential tail approximation for rejection sampling fallback

**calendar.py**: Calendar time and work-hour conversions
- `WorkCalendar` class initialized with start_date
- `add_work_hours(start_datetime, work_hours, hours_per_day) -> datetime`
- `calculate_work_hours_between(start, end, hours_per_day) -> float`
- `is_weekend(date) -> bool`

**scheduler.py**: Core scheduling and dependency logic
- `is_task_eligible(task, state) -> bool` - Check if task can start
- `get_eligible_workers(task, state) -> list[Worker]` - Find available workers
- `select_next_action(state, rng) -> Action | None` - Randomly choose next task/branch (uses RNG for ties)
- `detect_deadlock(state) -> bool` - Detect if simulation cannot progress

**state.py**: Track simulation state for one sample
- `WorkerState` dataclass: current_task, available_time
- `SimulationState` class: completed_tasks, resolved_branches, events, worker_states, failed_tasks

**engine.py**: Top-level orchestrator
- `SimulationEngine.__init__(num_samples, start_date, num_workers, hours_per_workday)`
- `SimulationEngine.run(project) -> Simulation`
- Main simulation loop calling scheduler
- Creates workers from num_workers and hours_per_workday
- Sequential execution (designed for future parallelization)

## Implementation Order

### Phase 1: Foundation Utilities (4-6 hours)

**1. distributions.py**
- Implement ShiftedLognormal parameter conversion algorithm:
  - Given (min, mode, p95), solve for (shift, mu, sigma)
  - Use quadratic equation: σ² + 1.645σ - ln(p95/mode) = 0
  - mu = ln(mode_unshifted) + σ²
  - shift = min
- Implement Triangular sampling using `numpy.random.triangular`
- Implement rejection sampling: keep sampling until value >= min_value
- Unit tests with known distributions

**2. calendar.py**
- Implement weekend detection (weekday >= 5)
- Implement work hour addition:
  - Given start datetime, add work hours considering weekends
  - Skip Saturday/Sunday when accumulating hours
- Implement work hour calculation between two datetimes
- Unit tests with various date ranges

### Phase 2: State Management (2-3 hours)

**3. state.py**
- Define `WorkerState` dataclass
- Implement `SimulationState` class:
  - Initialize from Project
  - Track completed tasks, resolved branches
  - Track worker availability
  - Methods: complete_task(), resolve_branch(), add_event()
- Unit tests for state transitions

### Phase 3: Core Scheduling Logic (8-10 hours - MOST COMPLEX)

**4. scheduler.py**

**Key Algorithm: Dependency Checking**
```python
def is_task_eligible(task: Task, state: SimulationState) -> bool:
    # 1. Not already completed or in progress
    if task.id in state.completed_tasks:
        return False

    # 2. Check all dependencies satisfied
    for dep in task.dependencies:
        target_id = dep.target_node_id

        # If target is a task
        if is_task_node(target_id):
            if dep.target_endpoint == Endpoint.END:
                # Target must be completed
                if target_id not in state.completed_tasks:
                    return False
            elif dep.target_endpoint == Endpoint.START:
                # Target must have started
                if not has_started(target_id, state):
                    return False

        # If target is a branch/possible world
        elif is_branch_node(target_id):
            branch_id = get_branch_id(target_id)
            if branch_id not in state.resolved_branches:
                return False
            # If dependency on specific possible world, check if chosen
            if is_possible_world(target_id):
                if state.resolved_branches[branch_id] != target_id:
                    return False  # Task not in chosen world

    # 3. Check eligible workers available
    eligible_workers = get_eligible_workers(task, state)
    if not eligible_workers:
        return False

    return True
```

**Key Algorithm: Worker Eligibility**
- Respect allowed_workers constraint
- Respect excluded_worker_tasks constraint
- Only assign available workers (current_task is None)

**Key Algorithm: Deadlock Detection**
- All workers idle (no current_task)
- Remaining tasks exist
- No remaining tasks are eligible
- Return failed_task_ids list

Implement all scheduler functions with comprehensive tests.

### Phase 4: Single-Sample Execution (6-8 hours)

**5. engine.py - Complete Implementation**

**Main Simulation Loop**:
```python
def run_single_sample(
    project: Project,
    start_date: datetime,
    sample_id: int,
    rng: np.random.Generator,
) -> Sample:
    state = SimulationState(project, start_date)
    calendar = WorkCalendar(start_date)
    events = []

    # Handle in-progress tasks first
    for task in get_in_progress_tasks(project):
        assign_in_progress_task(task, state, calendar, rng)

    # Main simulation loop
    while True:
        # Check for task completions at current time
        process_task_completions(state)

        # Select next action (task to start or branch to resolve)
        # Uses RNG to randomly choose when multiple options are available
        action = select_next_action(state, rng)
        if action:
            if action.type == "resolve_branch":
                resolve_branch(action.branch, state, rng)
            elif action.type == "start_task":
                start_task(action.task, state, calendar, rng)
            continue

        # No actions possible, check for deadlock or completion
        if detect_deadlock(state):
            return create_failed_sample(sample_id, state)

        if all_tasks_completed(state):
            return create_successful_sample(sample_id, state)

        # Advance time to next event
        advance_to_next_event(state)
```

**Design for Future Parallelization**:
- `run_single_sample()` is pure function (no shared state)
- Takes explicit RNG as parameter
- Returns complete Sample object
- Can be called in parallel processes later

Implement full simulation loop with event recording.

### Phase 5: Integration and Testing (4-5 hours)

**6. Engine Integration**
- Implement `SimulationEngine.run()` to call `run_single_sample()` sequentially
- Create simulation object with results
- Write comprehensive tests:
  - Simple linear DAG (3 tasks in sequence)
  - Parallel DAG (diamond pattern)
  - Branch with possible worlds
  - Worker constraints
  - Deadlock scenarios
  - In-progress tasks

## Key Algorithms

### ShiftedLognormal Parameter Conversion

Given ShiftedLognormal(min, mode, p95), compute (shift, mu, sigma) for numpy:

```
shift = min
mode_unshifted = mode - shift
p95_unshifted = p95 - shift

From lognormal properties:
- mode: exp(mu - σ²) = mode_unshifted
- p95: exp(mu + 1.645σ) = p95_unshifted  (1.645 is z-score for 95th percentile)

Taking logarithms:
- mu - σ² = ln(mode_unshifted)  ... (1)
- mu + 1.645σ = ln(p95_unshifted)  ... (2)

Subtract (1) from (2):
σ² + 1.645σ = ln(p95_unshifted / mode_unshifted)

Solve quadratic: σ² + 1.645σ - ln(p95/mode) = 0
σ = (-1.645 + sqrt(1.645² + 4*ln(p95/mode))) / 2

From (1): mu = ln(mode_unshifted) + σ²

Sample: shift + numpy.random.lognormal(mu, sigma)
```

### Rejection Sampling

For in-progress tasks with elapsed work-hours E:

```python
max_attempts = 1000
for _ in range(max_attempts):
    sample = sample_from_distribution(dist, rng)
    if sample >= elapsed_hours:
        return sample

# Fallback if can't sample (elapsed time way in tail)
# Approximate conditional distribution of tail with exponential
# P(X | X >= e) ≈ e + Exp(λ) where λ = 1/mean_of_original
mean_original = estimate_mean(dist)  # From distribution parameters
lambda_rate = 1.0 / mean_original
tail_sample = rng.exponential(scale=1.0/lambda_rate)
return elapsed_hours + tail_sample
```

### Weekend Handling

```python
def add_work_hours(start: datetime, hours: float, hours_per_day: float) -> datetime:
    current = start
    hours_remaining = hours

    while hours_remaining > 0:
        if is_weekend(current):
            # Skip to Monday
            current = skip_to_monday(current)
            continue

        # Add hours today (up to hours_per_day)
        hours_today = min(hours_remaining, hours_per_day)
        current += timedelta(hours=hours_today)
        hours_remaining -= hours_today

        if hours_remaining > 0:
            # Move to next workday
            current = start_of_next_workday(current)

    return current
```

## Testing Strategy

### Test Files Structure
```
tests/simulation/
├── test_distributions.py       # Test sampling functions
├── test_calendar.py            # Test calendar utilities
├── test_scheduler.py           # Test scheduling logic
├── test_state.py               # Test state management
├── test_engine.py              # Integration tests
└── fixtures.py                 # Reusable DAG fixtures
```

### Critical Test Cases

**Distributions**:
- ShiftedLognormal samples >= min
- Triangular samples in [min, max]
- Rejection sampling produces values >= threshold

**Calendar**:
- Adding work hours across weekends
- Multi-week time spans
- Boundary cases (start/end on weekend)

**Scheduler**:
- Linear dependency chain (A → B → C)
- Parallel tasks (A → C, B → C)
- Branch dependencies (task depends on possible world)
- Worker constraints (allowed_workers, excluded_worker_tasks)
- Deadlock detection with various scenarios

**Engine (Integration)**:
- Simple 3-task linear DAG completes successfully
- Diamond DAG with parallel paths
- Branch resolution and world selection
- Worker exclusions handled correctly
- In-progress task uses actual_assignee and rejection sampling
- Deadlock detected and failed_tasks recorded

### Test Fixtures

Create reusable DAG fixtures:
- `simple_linear_dag`: T1 → T2 → T3
- `diamond_dag`: T1 → (T2, T3) → T4
- `branch_dag`: Task depends on branch possible world
- `worker_constraint_dag`: Tasks with allowed_workers and exclusions

## Critical Edge Cases

1. **Empty DAG**: Simulation completes immediately with no events
2. **No workers**: All samples fail with deadlock
3. **In-progress tasks**: Use actual_assignee, rejection sampling for duration
4. **Worker exclusions create deadlock**: All workers excluded for a task
5. **Branch all resolves same way**: Valid but unusual statistics
6. **Very long simulation**: Monitor memory usage with large event lists

## Data Structures

```python
@dataclass
class WorkerState:
    worker_id: WorkerId
    hours_per_workday: float
    current_task: TaskId | None = None
    available_time: datetime = field(default_factory=lambda: datetime.now(UTC))

class SimulationState:
    def __init__(self, project: Project, start_date: datetime):
        self.project = project
        self.current_time = start_date
        self.completed_tasks: set[TaskId] = set()
        self.resolved_branches: dict[BranchId, PossibleWorldId] = {}
        self.events: list[TaskEvent] = []
        self.worker_states: dict[WorkerId, WorkerState] = {...}
        self.failed_tasks: list[TaskId] = []
```

## Worker Management Simplification

For this iteration, we'll simplify worker management to avoid full worker constraint implementation:

**Approach**:
- Simulation dialog asks for:
  - Number of workers (integer)
  - Hours per workday (float)
- Engine creates simple worker objects: `Worker(id=f"worker_{i}", name=f"Worker {i}", hours_per_workday=hours)`
- Store in SimulationState as `workers: list[Worker]`

**Deferred to later**:
- allowed_workers whitelist (ignore for now, all workers can do all tasks)
- excluded_worker_tasks constraints (ignore for now)
- Real worker management from Project.workers

**Implementation**:
```python
def create_workers(num_workers: int, hours_per_day: float) -> list[Worker]:
    return [
        Worker(
            id=WorkerId(f"sim_worker_{i}"),
            name=f"Worker {i+1}",
            hours_per_workday=hours_per_day
        )
        for i in range(num_workers)
    ]
```

This simplification lets us focus on core simulation logic. Worker constraints can be added later without changing the fundamental architecture.

## Implementation Notes

### Future Parallelization Considerations

Design `run_single_sample()` to be parallelization-ready:
- **Pure function**: No shared mutable state
- **Explicit RNG**: Pass numpy RNG as parameter (not global state)
- **Self-contained**: Returns complete Sample object
- **No I/O**: All inputs from parameters, all outputs in return value

When adding parallelization later:
```python
# Future implementation
with multiprocessing.Pool(num_processes) as pool:
    args = [(project, start_date, i, create_rng(i)) for i in range(num_samples)]
    samples = pool.starmap(run_single_sample, args)
```

### Deterministic Testing

Support seeded RNG for reproducible tests:
```python
rng = numpy.random.default_rng(seed=42)
sample = run_single_sample(project, start_date, 0, rng)
```

### Logging

Add structured logging for debugging:
```python
logger.debug(f"Task {task_id} started at {current_time} by {worker_id}")
logger.info(f"Sample {sample_id} completed with {len(events)} events")
logger.warning(f"Deadlock detected: tasks {failed_task_ids} cannot complete")
```

## Critical Files

### Create New
- `/home/kind/Prj/ProjectFluxx/src/fluxx/simulation/distributions.py`
- `/home/kind/Prj/ProjectFluxx/src/fluxx/simulation/calendar.py`
- `/home/kind/Prj/ProjectFluxx/src/fluxx/simulation/scheduler.py`
- `/home/kind/Prj/ProjectFluxx/src/fluxx/simulation/state.py`

### Modify Existing
- `/home/kind/Prj/ProjectFluxx/src/fluxx/simulation/engine.py` - Complete implementation
- `/home/kind/Prj/ProjectFluxx/tests/test_simulation.py` - Expand with comprehensive tests

### Reference (Read Only)
- `/home/kind/Prj/ProjectFluxx/src/fluxx/data/models.py` - Data schemas
- `/home/kind/Prj/ProjectFluxx/src/fluxx/data/validation.py` - DAG traversal patterns
- `/home/kind/Prj/ProjectFluxx/src/fluxx/data/dag_operations.py` - Project structure

## Estimated Timeline

- Phase 1 (Distributions + Calendar): 4-6 hours
- Phase 2 (State Management): 2-3 hours
- Phase 3 (Scheduler): 8-10 hours
- Phase 4 (Engine): 6-8 hours
- Phase 5 (Integration/Testing): 4-5 hours

**Total: 24-32 hours**

Most complexity is in scheduler (dependency checking, worker management, deadlock detection).
