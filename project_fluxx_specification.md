# Project Fluxx - Technical Specification

## 1. Overview

Project Fluxx is project planning software that incorporates uncertainty for tasks and samples from the schedule distribution to produce Gantt charts based on customizable levels of certainty (for management) and more fluid timeline visualizations (for me).

## 2. Core Concepts

### 2.1 Nodes

The system has two types of nodes:

**Task Nodes**: Represent work to be done. Tasks can have:
- Subtasks (all must be completed for the super-task to be completed)
- Duration distributions (for leaf tasks only)
- Dependencies on other tasks or branch possible worlds
- Worker constraints

**Branch Nodes**: Represent uncertain conditions/events (e.g., choosing between software options, approval decisions). Branches have:
- A discrete probability distribution over possible worlds
- An occurrence point (no duration)
- Dependencies like tasks

### 2.2 Duration Distributions

Leaf tasks must have a duration distribution. Initial implementations will support:

1. **Shifted Lognormal**: Specified by min, mode, and 95th percentile (fixed percentile)
   - A shifted lognormal is a lognormal whose minimum is shifted from 0 to some other value by adding a constant
   - If $L$ is a lognormally distributed random variable, $S = L + 5$ is a shifted lognormal with a minimum of 5

2. **Triangular**: Specified by min, mode, and max

Additional distributions will be added over time.

### 2.3 Possible Worlds

Branch nodes define multiple possible worlds (outcomes). Each possible world has:
- Title
- Description (optional)
- Weight (probability = weight / sum of all weights)

Tasks can depend on specific possible worlds, meaning they only need to be done in sampling runs where that possible world is chosen.

### 2.4 Workers

Workers have:
- Name
- ID (to distinguish workers with the same name)
- Description (optional)
- Hours per workday

## 3. Data Model

### 3.1 Task Node Schema

```
Task {
  id: unique identifier
  title: string
  description: string
  node_type: "task"
  parent_id: optional task id
  children: list of task ids

  # Duration (for leaf tasks only)
  duration_distribution: {
    type: "shifted_lognormal" | "triangular"
    parameters: distribution-specific parameters
  }

  # Dependencies
  dependencies: list of {
    source_endpoint: "start" | "end"
    target_node_id: task id or possible world id
    target_endpoint: "start" | "end" | "occurrence_point"
    constraint_type: ">=" | "="
  }

  # Worker constraints
  allowed_workers: optional list of worker ids (if absent, all allowed)
  excluded_worker_tasks: list of task ids whose assignees cannot be assigned to this task

  # Completion tracking
  is_done: boolean
  actual_start_time: optional datetime
  actual_duration: optional duration
}
```

### 3.2 Branch Node Schema

```
Branch {
  id: unique identifier
  title: string
  description: string
  node_type: "branch"

  # Possible worlds
  possible_worlds: list of {
    id: unique identifier
    title: string
    description: string
    weight: float
  }

  # Dependencies (on occurrence point)
  dependencies: list of {
    target_node_id: task id or possible world id
    target_endpoint: "start" | "end" | "occurrence_point"
    constraint_type: ">=" | "="
  }

  # Completion tracking
  is_done: boolean
  chosen_world_id: optional possible world id
}
```

### 3.3 Worker Schema

```
Worker {
  id: unique identifier
  name: string
  worker_id: string (for distinguishing same-named workers)
  description: optional string
  hours_per_workday: float
}
```

### 3.4 Simulation Schema

```
Simulation {
  id: unique identifier
  dag_snapshot: snapshot of DAG state when simulation was created
  start_date: datetime
  num_samples: integer
  num_parallel_processes: integer (default: 2 * num_processors)

  # Results
  samples: list of {
    sample_id: integer
    status: "success" | "failed"
    events: list of task/branch events with timestamps
    failed_tasks: optional list (if status = "failed")
  }

  # Statistics (computed from samples)
  task_statistics: map of task_id to {
    percentiles: map of percentile to {start_time, end_time, duration}
    min_start: datetime
    max_end: datetime
  }

  failure_rate: float (fraction of failed runs)
}
```

## 4. User Interface

### 4.1 Overall Layout

The application window is divided into two main panels:

1. **DAG Panel** (left/main area): Displays the task/branch graph with controls
2. **Editor Panel** (right/side area): Displays details and controls for the selected node

### 4.2 DAG Panel

#### 4.2.1 Control Bar

Located above the DAG view, contains:
- **View Mode Toggle**: Radio buttons to switch between DAG display and list display
- **Add Root Node**: Button to create a new node with no parent
- **View Simulations**: Button to open simulation management (displays in editor panel)
- **Edit Workers**: Button to open worker list editor (displays in editor panel)

#### 4.2.2 DAG Display Mode

**Layout**:
- Auto-laid-out graph of nodes and dependencies
- User can pan and zoom
- Collapsible nodes (to hide subtasks)

**Node Rendering**:

*Task Nodes*:
- Box with title
- Description visible on hover
- Visual indicators for completion status

*Branch Nodes*:
- Dot representing the occurrence point
- Lines connecting to boxes for each possible world
- Each possible world box shows title

**Dependency Rendering**:
- Arrow from source endpoint to target endpoint
- Standard dependencies: simple arrows
- Equality constraints: double-ended arrows
- Assignee exclusions: purple line with 🚫 symbol pointing to the task whose assignee is excluded

**Interaction**:
- Click on a node to select it (opens in editor panel)
- Click on a possible world box to select it as dependency target

#### 4.2.3 List Display Mode

**Layout**:
- List of all nodes with titles
- Search bar to filter by substring

**Interaction**:
- Clicking a node switches back to DAG display with the node centered

### 4.3 Editor Panel

#### 4.3.1 Panel Structure

**Header** (upper left):
- Current history event display
- Dropdown button to show history tree view for navigation

**Content Area**:
- Fields specific to the selected node type
- Input controls (text boxes, dropdowns, lists)

**Footer**:
- **Apply** button: Commits changes
- **Revert** button: Discards unapplied changes
- **Delete Node** button: Deletes the node

#### 4.3.2 Task Node Editor

**Basic Fields**:
- Title (text input)
- Description (text area)

**Duration Distribution** (leaf tasks only, required):
- Distribution type selector
- Parameter inputs based on type:
  - Shifted lognormal: min, mode, 95th percentile
  - Triangular: min, mode, max

**Dependencies Section**:
- List of current dependencies, each showing:
  - Source endpoint, constraint type, target node/world, target endpoint
  - Click to edit
  - Trashcan icon to delete
- **Add Dependency** button

**Worker Constraints Section**:
- **Allowed Workers**:
  - If empty: "All workers allowed. [Click to add reduced list of allowed workers]"
  - If populated: List with + button to add, trashcan to remove
- **Excluded Assignees**:
  - List of tasks whose assignees cannot be assigned here
  - + button to add task, trashcan to remove

**Subtask Management** (leaf tasks):
- **Convert to Parent** button: Adds first child and navigates to it

**Subtask Management** (parent tasks):
- Children have **Add Sibling** button in their editors

**Completion Tracking**:
- **Mark as Done** checkbox/section
- If done: Start time and duration inputs

#### 4.3.3 Branch Node Editor

**Basic Fields**:
- Title (text input)
- Description (text area)

**Possible Worlds Section**:
- Table with columns: Title, Description, Weight, Probability (computed), Actions
- Each row has a trashcan icon to delete
- Bottom row is blank; clicking any cell creates a new possible world
- Probability auto-updates as weight / sum(weights)

**Dependencies Section**:
- Similar to task dependencies, but source endpoint is always "occurrence point"
- List of current dependencies with edit/delete options
- **Add Dependency** button

**Completion Tracking**:
- **Mark as Done** checkbox/section
- If done: Which possible world occurred (dropdown)

#### 4.3.4 Edit Modes

**Edit Dependency Mode**:

Activated when adding or editing a dependency. Shows:
- Source endpoint dropdown (start/end, or "occurrence point" for branches)
- Target endpoint dropdown (start/end, or auto-set to "occurrence point" if target is possible world)
- Constraint type dropdown (>= or =)
- **Select Target** button

When selecting target:
- Enter "select-target-node mode"
- Other editing and DAG modifications are disabled
- User navigates DAG (or list view) and clicks on a target node/possible world box
- Can cancel to abort selection

**Select Task Node Mode**:

Used when adding excluded assignee tasks. Similar to select-target-node mode but only task nodes are selectable.

#### 4.3.5 Navigation and Change Management

**Navigation**:
- Clicking a different node while editing triggers a modal if there are unapplied changes:
  - Apply changes and navigate
  - Revert changes and navigate
  - Cancel navigation

**Validation**:
- Apply button disabled until all required fields are filled and consistent
- Invalid controls are highlighted
- Error message at top of editor explains one issue and how to fix it

**New Node Handling**:
- Reverting a new node deletes it and returns to previously selected node

**Node Deletion**:
- Deletes the node and all its dependencies
- For parent nodes: Cascade deletes all children
  - Confirmation modal: "This node has X children, are you sure you want to delete them and any attached dependencies? (Y/N)"
- Simulations retain references to nodes as they existed when the simulation ran

### 4.4 Worker List Editor

Opened from DAG panel button bar, displays in editor panel (a "navigate away" event).

**Layout**:
- Table with columns: Name, ID, Description, Hours per Workday
- Each field is editable
- Bottom row is blank; clicking creates a new worker

**Validation**:
- Name and Hours per Workday are required
- ID must be filled if multiple workers share the same name
- Description is optional

**Footer**:
- Apply and Revert buttons

### 4.5 Simulation Management

Opened from DAG panel button bar, displays in editor panel.

**Simulation List**:
- Shows all simulations for current DAG
- Each entry displays:
  - Simulation ID/name
  - Number of samples
  - Failure rate (if any failures)
  - Status (running/complete)
- **Create New Simulation** button

**Creating a Simulation**:

Dialog collects:
- Number of samples (e.g., 1000)
- Start date (default: start of workday after current date)
- Number of parallel processes (default: 2 × number of processors)

**Running Simulation**:

Progress display shows:
- Elapsed time
- Estimated time to completion
- Current sample count / target sample count
- Progress bar with early stop button

**Simulation Actions**:
- **Add More Samples**: Adds additional samples to completed simulation
- **Generate Gantt Chart**: Opens dialog to set percentile (default 97%)
- **Generate Probabilistic Timeline**: Opens dialog to set percentile (default 90%)

**Visualization Display**:

After generation, visualization is displayed with options:
- **Save**: Opens file dialog to choose save location
- **Discard**: Closes visualization without saving

### 4.6 History and Undo/Redo

**History Display** (upper left of editor panel):
- Shows most recent history event
- Dropdown shows tree view of history

**History Tree**:
- Each event is a node
- Branching occurs when undo followed by different action
- Events include timestamps
- Extended events (simulations) include duration

**Keyboard Shortcuts**:
- **CTRL-Z**: Undo (navigate to parent history node)
- **CTRL-Y**: Redo (navigate to child with most recent leaf descendant)

**Context Sensitivity**:
- When editor control has focus: CTRL-Z/Y operate on the control
- When no control has focus or no unapplied changes: CTRL-Z/Y operate on history

**Simulation Reproducibility**:
- History nodes with simulations store the random seed/state
- Reloading doesn't require regeneration - ensures reproducibility across versions

## 5. Dependencies and Constraints

### 5.1 Task-Task Dependencies

Task endpoints can depend on other task endpoints with two constraint types:

1. **Greater-than-or-equal (>=)**: Target endpoint time ≥ source endpoint time
2. **Equality (=)**: Target endpoint time = source endpoint time

Most common: Task B start time ≥ Task A end time (Task B starts after Task A finishes)

### 5.2 Parent-Child Constraints

Automatically enforced for subtasks:
- Subtask start time ≥ parent start time
- Parent end time ≥ subtask end time

### 5.3 Possible World Dependencies

Tasks can depend on one or more branch possible worlds:
- Represented as individual dependencies
- Task only executes in sampling runs where one of its dependent possible worlds is chosen

### 5.4 Worker Constraints

**Allowed Workers Whitelist**:
- If specified, only listed workers can be assigned during simulation
- If absent, any worker can be assigned

**Excluded Assignees**:
- List of tasks whose assigned workers cannot be assigned to this task
- Referenced tasks must have a starts-at-or-before dependency so their assignees are known in simulation

### 5.5 Constraint Validation

**Cycle Detection**:
- Dependency graph must be acyclic
- System should detect and prevent cycle creation

**Temporal Consistency**:
- All dependencies must be satisfiable
- System should validate before allowing simulation

## 6. Simulation Engine

### 6.1 Simulation Parameters

- **Number of samples**: How many runs to simulate (e.g., 1000)
- **Start date**: When the project begins (default: start of next workday)
- **Parallel processes**: Number of simultaneous simulations (default: 2 × CPU count)

### 6.2 Simulation Mechanics

**Calendar Tracking**:
- Tracks time on a calendar
- Weekends exist (no work done)
- Holidays will be added in future

**Worker Simulation**:
- Each worker has hours/workday and current task assignment
- Workers work on one task at a time until completion
- When no workers available, no new tasks can start

**Task Assignment**:
- Parent tasks don't get assigned (work is in subtasks)
- Parent task duration determined implicitly by subtasks
- Worker constraints enforced:
  - Must be in allowed workers list (if specified)
  - Cannot be assignee of excluded tasks

**Branch Resolution**:
- Branches resolve as soon as dependencies satisfied
- One possible world chosen based on probability distribution
- Tasks dependent on unchosen worlds are skipped for that run

**Task Selection**:
- When multiple tasks can start simultaneously:
  - All dependencies satisfied
  - Workers available who can do the task
  - One is randomly selected
- If task N excludes assignee of task M, assignment to M must happen first

**Parallel Execution**:
- Multiple simulation runs execute in parallel
- Number of parallel processes configurable
- Early stopping terminates all child processes

### 6.3 Failed Runs

A sampling run fails if:
- All workers are available
- No tasks are running
- Unfulfilled dependencies exist for tasks in current possible world

When a run fails:
- Save final state
- Mark as failed
- Record which tasks couldn't be completed
- Most likely cause: too many worker exclusions

**Failure Reporting**:
- Fraction of failed runs shown in simulation list
- User can inspect failed runs to see incomplete tasks

### 6.4 Incremental Sampling

- Can add more samples to a completed simulation
- Samples are independent, so can be generated separately
- Results are merged into existing simulation statistics

## 7. Visualizations

### 7.1 Gantt Charts

**Purpose**: Conservative timeline for management

**Algorithm**:

1. User selects percentile P (default 97%)
2. For each task variant (tasks on different branch paths are separate):
   - Compute Pth percentile start time from samples
   - Compute Pth percentile duration from samples
3. Solve optimization problem (linear programming):
   - Assign start time and duration to each task
   - Must satisfy all dependencies
   - Start time ≥ Pth percentile start time
   - Duration ≥ Pth percentile duration
   - Minimize some objective (e.g., total project duration)

**Properties**:
- Conservative: all dates at or after Pth percentile from samples
- Respects dependencies
- Feasible timeline

**Implementation Tool**: pyomo for linear programming

### 7.2 Probabilistic Timeline

**Purpose**: Show uncertainty visually

**Algorithm**:

1. User selects percentile P (default 90%)
2. For each task:
   - Show box with:
     - Minimum start time (across all samples)
     - Maximum end time (across all samples)
     - Pth percentile start time
     - Pth percentile end time
3. Draw dependency arrows:
   - Equality: double-ended arrow
   - Greater-than-or-equal: arrow from earlier to later (in time)
4. Branch points create sub-diagrams for each possible world's tasks

**Visual Encoding**:
- Box represents task temporal uncertainty
- Inner markers show percentile boundaries
- Arrows show dependency relationships
- Branch outcomes create parallel sub-diagrams

## 8. History System

### 8.1 History Event Tracking

Every change creates a history event:
- User actions (node edits, deletions, additions)
- Simulations (with execution time)
- Parameter changes

Each event records:
- Timestamp
- Duration (for extended operations)
- Changed data
- Previous state (for undo)

### 8.2 Branching History

**Linear History**:
- Normal undo/redo creates linear chain

**Branching**:
- Occurs when: undo, then make different change
- Both branches preserved
- Tree structure allows navigation to either

**Implementation**:
- History events form a tree
- Each event points to parent and children
- Current state is a leaf in the tree

### 8.3 Reproducibility

**Simulation Storage**:
- Store RNG seed/state with simulation
- Reloading simulation uses stored results
- No regeneration needed
- Ensures reproducibility even if simulation algorithm changes

**DAG Snapshots**:
- Simulations store snapshot of DAG at creation time
- Deleted nodes are preserved in simulation history
- References in simulations point to node versions at simulation time

## 9. Implementation Considerations

### 9.1 Technology Stack

**Language**: Python

**GUI Framework**: PyQt

**Testing**: pytest with 100% code coverage requirement for all code (including GUI)
- Exceptions only with explicit agreement

**Static Analysis**:
- **ruff**: Linting and code analysis
- **mypy**: Full type annotation enforcement
- **pydantic**: Data schema validation and enforcement

**Pre-commit Hooks**:
- Run static analysis before every commit
- Prevent commits that fail checks

**Optimization**: pyomo for linear programming (Gantt chart generation)

### 9.2 Code Quality Standards

**Type Safety**:
- All code must be fully type-annotated
- mypy must pass with no errors

**Testing**:
- 100% code coverage via pytest
- Unit tests for all components
- GUI tests for all user interactions

**Data Validation**:
- All data schemas defined with pydantic
- Validation at data boundaries
- Clear error messages for validation failures

**Code Style**:
- Enforced by ruff
- Must pass pre-commit checks

### 9.3 Architecture Recommendations

**Separation of Concerns**:
- Data model (pydantic schemas)
- Business logic (simulation, dependency validation, etc.)
- GUI layer (PyQt)
- Clear interfaces between layers

**Testability**:
- Business logic independent of GUI
- Dependency injection for testing
- Mock-able external dependencies

**Performance**:
- Parallel simulation execution
- Lazy loading where appropriate
- Efficient graph algorithms for dependency checking

## 10. Future Improvements

These features are planned but not part of the initial implementation:

### 10.1 Jira Integration

- Use past performance to constrain variance of task lengths
- Allow Jira plan updates as project plan updates
- Update timeline as tasks finish
- Discover new tasks from Jira
- Estimate costs of adding new tasks using history
- Associate tasks/branches with Jira issues
- Store metadata that doesn't map to Jira fields in attachments

### 10.2 Enhanced Task Features

- Review time and potential reviewers
- Worker affinities (different workers take different amounts of time)

### 10.3 Calendar Enhancements

- Holidays
- Vacations
- Custom work schedules

### 10.4 Enhanced Sampling

- Sample until all possible worlds happen at least K times
- Use pymc for sampling (enables oversampling rare worlds while keeping probabilities correct)

### 10.5 Visualization Enhancements

- Interactive hiding/showing of sub-tasks in Gantt charts
- Additional visualization types

## 11. Glossary

**DAG**: Directed Acyclic Graph - the structure of tasks and branches with dependencies

**Node**: Either a task or a branch in the DAG

**Endpoint**: Start or end point of a task (branches only have "occurrence point")

**Possible World**: One outcome of a branch node

**Sampling Run**: A single simulation of the project from start to finish

**Simulation**: A collection of many sampling runs with aggregated statistics

**Percentile**: A value below which a given percentage of observations fall (e.g., 97th percentile means 97% of observations are at or below this value)

**Shifted Lognormal**: A lognormal distribution with its minimum shifted from 0 to a specified value

**Worker Exclusion**: Constraint preventing a task from being assigned to the same worker as another task

**History Event**: A recorded change to the project state, allowing undo/redo
