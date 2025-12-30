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

Leaf tasks must have a duration distribution. **All durations are measured in work-hours**.

Initial implementations will support:

1. **Shifted Lognormal**: Specified by min, mode, and 95th percentile (fixed percentile), all in work-hours
   - A shifted lognormal is a lognormal whose minimum is shifted from 0 to some other value by adding a constant
   - If $L$ is a lognormally distributed random variable, $S = L + 5$ is a shifted lognormal with a minimum of 5 work-hours

2. **Triangular**: Specified by min, mode, and max, all in work-hours

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
- ID (optional, to distinguish workers with the same name)
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
  # Must be one of the DurationDistribution subclasses
  duration_distribution: ShiftedLognormal | Triangular

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
  # Task is done if actual_duration is present
  # actual_assignee and actual_start_time must be set together (task in progress or done)
  # actual_duration can only be set if actual_start_time is set
  actual_start_time: optional datetime
  actual_assignee: optional worker id
  actual_duration: optional float (work-hours)
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
  # Branch is done if chosen_world_id is present
  chosen_world_id: optional possible world id
}
```

### 3.3 Worker Schema

```
Worker {
  id: unique identifier
  name: string
  worker_id: optional string (for distinguishing same-named workers)
  description: optional string
  hours_per_workday: float  # Used to convert work-hours to calendar days
}
```

The `hours_per_workday` field is used to convert task durations (measured in work-hours) to calendar time. For example, if a worker has `hours_per_workday = 6.0` and a task has a duration of 12 work-hours, the task will take 2 workdays for that worker to complete.

### 3.4 Duration Distribution Schemas

Base class and subclasses for type-safe duration distributions:

```
class DurationDistribution:
  # Base class for all duration distributions
  pass

class ShiftedLognormal(DurationDistribution):
  min: float
  mode: float  # must be > min
  percentile_95: float  # must be > min

class Triangular(DurationDistribution):
  min: float
  mode: float  # must be > min
  max: float  # must be > mode
```

### 3.5 DAG and History Schemas

The DAG and history system use persistent objects to maintain references across versions:

```
DAG {
  id: unique identifier
  current_version_id: version id
  # Maps node ids to their current persistent object versions
  node_map: map of node_id to persistent_object_id
}

DAGEvent {
  id: unique identifier
  timestamp: datetime
  parent_event_id: optional event id
  # What changed
  event_type: "node_created" | "node_modified" | "node_deleted" | "simulation_created" | etc.
  affected_nodes: list of node ids
  # DAG state after this event
  resulting_dag_version: DAG version id
}

PersistentTask {
  id: unique identifier (never reused)
  versions: list of Task snapshots with version ids
}

PersistentBranch {
  id: unique identifier (never reused)
  versions: list of Branch snapshots with version ids
}
```

**Design Note**: When a simulation is created, it references the specific DAG version and persistent object versions that existed at that time. When nodes are deleted, their persistent objects remain in the database, ensuring simulations can always resolve their references.

### 3.6 Simulation Schema

```
Simulation {
  id: unique identifier
  dag_version_id: version id of DAG when simulation was created
  start_date: datetime
  num_samples: integer
  num_parallel_processes: integer (default: 2 * num_processors)

  # Completion status
  status: "running" | "completed" | "failed"
  completed_samples: integer  # How many samples have finished

  # Results stored for reproducibility (not regenerated)
  # Stores complete simulation results, not just RNG seed
  samples: list of {
    sample_id: integer
    events: list of task/branch events with timestamps
    failed_tasks: list of task ids (empty if successful)
  }

  # Checkpoint data (for resuming interrupted simulations)
  last_checkpoint: optional {
    timestamp: datetime
    completed_samples: integer
    rng_state: serialized RNG state for continuing
  }

  # Note: Percentiles and statistics are computed on-demand when generating
  # visualizations, not pre-calculated and stored
}
```

**Sample Status**: A sample is successful if `failed_tasks` is empty, otherwise failed. This makes illegal states unrepresentable.

**Checkpoint Strategy**: Rather than saving complete worker state during simulation execution, periodic snapshots are created. If a simulation is interrupted, it can be resumed from the last checkpoint by re-running samples since that checkpoint. This is much simpler than trying to persist complete execution state.

## 4. Project Persistence

### 4.1 File Format

Projects are saved as JSON files with a `.fluxx` extension.

**Structure**:
```
{
  "version": "1.0",
  "project_metadata": {
    "name": "Project Name",
    "created": "2024-01-15T10:30:00Z",
    "last_modified": "2024-01-20T14:22:00Z"
  },
  "workers": [...],
  "dag": {
    "current_version_id": "dag_v123",
    "node_map": {...}
  },
  "persistent_objects": {
    "tasks": {...},
    "branches": {...}
  },
  "history": {
    "events": [...],
    "current_event_id": "event_456"
  },
  "simulations": [...]
}
```

**Design Principles**:
- JSON for human readability and version control friendliness
- Pydantic models serialize/deserialize directly to/from JSON
- Complete history preserved (entire history tree, not just current state)
- Simulations store complete results for reproducibility

### 4.2 Saving

**Manual Save**:
- File → Save (CTRL-S) saves to current file
- File → Save As allows choosing new filename/location
- Default location: `~/Documents/ProjectFluxx/`
- Suggested filename: `<project_name>_<date>.fluxx`

**Auto-save**:
- Auto-save every 5 minutes (configurable)
- Saves to temporary file: `.fluxx_autosave/<project_name>_autosave.fluxx`
- On clean exit, auto-save file is deleted
- On crash/unclean exit, auto-save file is preserved

**Save Process**:
1. Serialize current state to JSON
2. Write to temporary file (`<filename>.tmp`)
3. Atomic rename to target filename
4. Update window title with saved status

### 4.3 Loading

**File → Open** (CTRL-O):
- Opens file picker
- Loads project from `.fluxx` file
- Validates file format and version
- Restores complete state including:
  - All workers
  - Complete DAG with all node versions
  - Full history tree
  - All simulations with results

**Recent Files**:
- File menu shows 5 most recent projects
- Quick access to recently worked on projects

**Recovery**:
- On startup, check for auto-save files
- If found, prompt user: "Found auto-saved work from [time]. Recover?"
- Options: Recover, Discard, Open Both

### 4.4 Version Compatibility

**Version String**: Saved in file as `"version": "1.0"`

**Forward Compatibility**:
- If file version > application version: warn user, may fail to load
- Display message: "This file was created with a newer version of Project Fluxx"

**Backward Compatibility**:
- If file version < application version: attempt migration
- Migration functions transform old format to new format
- Create backup before migration: `<filename>.backup_v<old_version>`

**Schema Validation**:
- Use Pydantic to validate structure on load
- Clear error messages for corrupted/invalid files
- Never lose data - always preserve original file

### 4.5 File Menu Structure

```
File
├── New Project          (CTRL-N)
├── Open...              (CTRL-O)
├── Recent Files         >
│   ├── project1.fluxx
│   ├── project2.fluxx
│   └── ...
├── ───────────
├── Save                 (CTRL-S)
├── Save As...           (CTRL-SHIFT-S)
├── ───────────
├── Export...            >
│   ├── Export to CSV
│   └── Export Gantt Chart
├── ───────────
└── Exit                 (CTRL-Q)
```

### 4.6 New Project

**File → New Project**:
- If current project has unsaved changes: prompt to save
- Initialize empty DAG
- Create default worker: "Worker 1" with 8 hours/day
- Set project name to "Untitled Project"
- First save will prompt for filename

### 4.7 Implementation Notes

**Data Consistency**:
- All IDs must be globally unique (use UUID)
- References between objects use IDs (never object references)
- Validate referential integrity on load

**Performance**:
- Large projects with many simulations can be >100MB
- Use streaming JSON parser for large files if needed
- Consider compression for simulation data

**Security**:
- No executable code in project files (pure data)
- Validate all inputs from file
- Sandbox deserialization (Pydantic helps with this)

## 5. User Interface

### 5.1 Overall Layout

The application window is divided into two main panels:

1. **DAG Panel** (left/main area): Displays the task/branch graph with controls
2. **Editor Panel** (right/side area): Displays details and controls for the selected node

### 5.2 DAG Panel

#### 5.2.1 Control Bar

Located above the DAG view, contains:
- **History Widget**: Small widget showing most recent history event with dropdown for history tree navigation
  - Displays brief description of current history state
  - Click dropdown to show history tree view for navigation
  - User can select which historical DAG version to view/edit
- **View Mode Toggle**: Radio buttons to switch between DAG display and list display
- **Add Root Node**: Button to create a new node with no parent
- **View Simulations**: Button to open simulation management (displays in editor panel)
- **Edit Workers**: Button to open worker list editor (displays in editor panel)

**Keyboard Shortcuts** (for history navigation):
- **CTRL-Z**: Undo (navigate to parent history node)
- **CTRL-Y**: Redo (navigate to child with most recent leaf descendant)

**Context Sensitivity**:
- When editor control has focus: CTRL-Z/Y operate on the control
- When no control has focus or no unapplied changes: CTRL-Z/Y operate on history

#### 5.2.2 DAG Display Mode

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
- Click on a task node to select it (opens in editor panel)
- Click on a possible world box to select its parent branch (opens in editor panel)
  - Exception: When in select-target-node mode, clicking selects it as dependency target

#### 5.2.3 List Display Mode

**Layout**:
- List of all nodes with titles
- Search bar to filter nodes using fuzzy matching (RapidFuzz library)
  - Nodes ranked by match quality

**Interaction**:
- Clicking a node switches back to DAG display with the node centered

### 5.3 Editor Panel

#### 5.3.1 Panel Structure

**Content Area**:
- Fields specific to the selected node type
- Input controls (text boxes, dropdowns, lists)

**Footer**:
- **Apply** button: Commits changes
- **Revert** button: Discards unapplied changes
- **Delete Node** button: Deletes the node

#### 5.3.2 Task Node Editor

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

**Subtask Management** (child tasks):
- **Add Sibling** button: Creates a new sibling task (child of same parent)

**Completion Tracking**:
- **Start Task** section: Start time and assignee inputs (marks task as in progress)
- **Complete Task** section: Duration input (only enabled if task is started)
  - Setting duration marks task as done
- **Note**: Tasks with actual_duration set are done; tasks with actual_start_time but no actual_duration are in progress

#### 5.3.3 Branch Node Editor

**Basic Fields**:
- Title (text input)
- Description (text area)

**Possible Worlds Section**:
- Table with columns: Title, Description, Weight, Probability (computed), Actions
- Each row has a trashcan icon to delete
- Bottom row is blank; clicking any cell creates a new possible world
- Blank weights are treated as 0
- Probability auto-updates as weight / sum(weights)

**Dependencies Section**:
- Similar to task dependencies, but source endpoint is always "occurrence point"
- List of current dependencies with edit/delete options
- **Add Dependency** button

**Completion Tracking**:
- **Resolve Branch** section: Dropdown to select which possible world occurred
  - Setting chosen_world_id marks the branch as resolved/done

#### 5.3.4 Edit Modes

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

#### 5.3.5 Navigation and Change Management

**Navigation**:
- Clicking a different node while editing triggers a modal if there are unapplied changes:
  - Apply changes and navigate
  - Revert changes and navigate
  - Cancel navigation

**Validation**:
- Apply button disabled until all required fields are filled and consistent
- Invalid controls are highlighted
- Error message at top of editor explains one issue and how to fix it
- **Dependency validation**: Adding a dependency is checked to ensure it does not create a cycle
  - If cycle detected, the dependency cannot be added and user is shown an error

**New Node Handling**:
- Reverting a new node deletes it and returns to previously selected node

**Node Deletion**:
- Deletes the node and all its dependencies
- For parent nodes: Cascade deletes all children
  - Confirmation modal: "This node has X children, are you sure you want to delete them and any attached dependencies? (Y/N)"
- Simulations retain references to nodes as they existed when the simulation ran

### 5.4 Worker List Editor

Opened from DAG panel button bar, displays in editor panel (a "navigate away" event).

**Layout**:
- Table with columns: Name, ID, Description, Hours per Workday
- Each field is editable
- Bottom row is blank; clicking creates a new worker

**Validation**:
- Name and Hours per Workday are required
- ID is optional, but must be filled if multiple workers share the same name
- Description is optional

**Footer**:
- Apply and Revert buttons

### 5.5 Simulation Management

Opened from DAG panel button bar, displays in editor panel.

**Simulation List**:
- Shows all simulations for current DAG
- Each entry displays:
  - Simulation ID/name
  - Number of samples (completed/target for incomplete)
  - Failure rate (if any failures)
  - Status (running/completed/interrupted)
- **Create New Simulation** button
- For interrupted simulations: **Resume** button appears

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
- Last checkpoint time (if checkpoints enabled)

**Resuming Interrupted Simulation**:

When clicking Resume on an interrupted simulation:
- Confirms: "Resume from checkpoint at X/Y samples?"
- Continues from last checkpoint
- Shows same progress display as new simulation
- Can early stop or let complete

**Simulation Actions**:
- **Add More Samples**: Adds additional samples to completed simulation
- **Generate Gantt Chart**: Opens dialog to set percentile (default 97%)
- **Generate Probabilistic Timeline**: Opens dialog to set percentile (default 90%)

**Visualization Display**:

After generation, visualization is displayed with options:
- **Save**: Opens file dialog to choose save location
- **Discard**: Closes visualization without saving

### 5.6 History Tree Navigation

**History Tree Structure**:
- Each event is a node in the tree
- Branching occurs when undo followed by different action
- Events include timestamps
- Extended events (simulations) include duration

See section 5.2.1 for history display UI and keyboard shortcuts.

## 6. Dependencies and Constraints

### 6.1 Task-Task Dependencies

Task endpoints can depend on other task endpoints with two constraint types:

1. **Greater-than-or-equal (>=)**: Target endpoint time ≥ source endpoint time
2. **Equality (=)**: Target endpoint time = source endpoint time

Most common: Task B start time ≥ Task A end time (Task B starts after Task A finishes)

### 6.2 Parent-Child Constraints

**Implementation Note**: Parent-child temporal constraints should be represented as explicit dependencies in the dependency graph (not special-cased). This simplifies the implementation and makes the dependency graph complete.

When a subtask is created:
- Automatically add dependency: subtask.start >= parent.start
- Automatically add dependency: parent.end >= subtask.end

These dependencies are maintained automatically by the system but can be viewed like other dependencies.

### 6.3 Possible World Dependencies

Tasks can depend on one or more branch possible worlds:
- Represented as individual dependencies
- Task only executes in sampling runs where one of its dependent possible worlds is chosen

### 6.4 Worker Constraints

**Allowed Workers Whitelist**:
- If specified, only listed workers can be assigned during simulation
- If absent, any worker can be assigned

**Excluded Assignees**:
- List of tasks whose assigned workers cannot be assigned to this task
- **Required dependency**: If task N excludes the assignee of task M, there must be a dependency: N.start >= M.start
  - This ensures M's assignee is known before N starts in the simulation
  - System should validate this constraint and prevent adding exclusions without the dependency

### 6.5 Constraint Validation

**Cycle Detection**:
- Dependency graph must be acyclic
- System should detect and prevent cycle creation

**Temporal Consistency**:
- All dependencies must be satisfiable
- System should validate before allowing simulation

## 7. Simulation Engine

### 7.1 Simulation Parameters

- **Number of samples**: How many runs to simulate (e.g., 1000)
- **Start date**: When the project begins (default: start of next workday)
- **Parallel processes**: Number of simultaneous simulations (default: 2 × CPU count)

### 7.2 Simulation Mechanics

**Calendar Tracking**:
- Tracks time on a calendar
- Weekends exist (no work done)
- Holidays, vacations, and sick days will be added in future

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

**Tasks in Progress**:
- If a task has actual_start_time and actual_assignee but no actual_duration, it's in progress
- During simulation, the task must:
  - Be assigned to the actual_assignee (not a random worker)
  - Use rejection sampling for duration: sample from distribution and reject durations < elapsed time
  - Elapsed time = work hours between actual_start_time and simulation start
  - This ensures the simulated duration is consistent with the task already being in progress

**Branch Resolution**:
- Branches resolve as soon as dependencies satisfied
- One possible world chosen based on probability distribution
- Tasks dependent on unchosen worlds are skipped for that run

**Task Selection**:
- When multiple tasks can start simultaneously:
  - All dependencies satisfied
  - Workers available who can do the task
  - One is randomly selected
- **Worker Exclusion Handling**: If task N excludes the assignee of task M:
  - The required dependency (N.start >= M.start) ensures M is assigned before N starts
  - When N becomes eligible, M's assignee is already known and can be excluded from N's candidate workers

**Parallel Execution**:
- Multiple simulation runs execute in parallel
- Number of parallel processes configurable
- Early stopping terminates all child processes

### 7.3 Failed Runs

A sampling run fails if:
- All workers are available
- No tasks are running
- ALL remaining tasks in the current possible world have unfulfilled dependencies

This indicates a deadlock: the simulation cannot progress because no new task can start.

When a run fails:
- Save final state
- Mark as failed
- Record which tasks couldn't be completed
- Most likely cause: too many worker exclusions

**Failure Reporting**:
- Fraction of failed runs shown in simulation list
- User can inspect failed runs to see incomplete tasks

### 7.4 Incremental Sampling

- Can add more samples to a completed simulation
- Samples are independent, so can be generated separately
- Results are merged into existing simulation statistics

### 7.5 Checkpointing and Resuming

**Checkpoint Creation**:
- Periodic snapshots created during long-running simulations
- Checkpoint frequency: every 100 completed samples (configurable)
- Checkpoint contains:
  - Number of completed samples
  - All completed sample results
  - RNG state for continuing from this point
  - Timestamp

**Resuming Interrupted Simulations**:
- On application startup or project load, check for incomplete simulations
- If found: display "Resume simulation with X/Y samples completed?"
- On resume:
  - Load last checkpoint
  - Restore RNG state
  - Continue from completed_samples count
  - Re-run any samples that were in progress when interrupted

**Benefits of Checkpoint Approach**:
- Much simpler than saving complete worker/task state during execution
- Minimal overhead (just sample results and RNG state)
- Can resume from any checkpoint if earlier ones are preserved
- Failed/crashed simulations don't lose all work

**Auto-save Integration**:
- Checkpoints are saved with the project file
- Auto-save captures latest checkpoint
- On crash recovery, can resume simulation from last auto-saved checkpoint

**Implementation Notes**:
- Each parallel process maintains its own RNG state
- Checkpoint saves all process RNG states as array
- Sample IDs must be deterministic (not based on timestamp)
- Use sample_id = checkpoint_count * 100 + local_sample_id for reproducibility

## 8. Visualizations

### 8.1 Gantt Charts

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
   - Minimize: sum of all start times + sum of all durations (possibly with scaling factor)
     - This objective avoids computing the critical path while still producing reasonable timelines

**Properties**:
- Conservative: all dates at or after Pth percentile from samples
- Respects dependencies
- Feasible timeline

**Implementation Tool**: pyomo for linear programming

### 8.2 Probabilistic Timeline

**Purpose**: Show uncertainty visually

**Algorithm**:

1. User selects percentile P (default 90%)
2. For each task, show box with:
   - Minimum start time (across all samples)
   - Maximum end time (across all samples)
   - (1-P)th percentile start time (e.g., if P=90%, show 10th percentile start)
   - Pth percentile end time
   - This shows the range where the task is likely to occur
3. Draw dependency arrows:
   - Equality: double-ended arrow
   - Greater-than-or-equal: arrow from earlier to later (in time)
4. Branch points create sub-diagrams for each possible world's tasks

**Visual Encoding**:
- Box represents task temporal uncertainty
- Outer boundaries: minimum start to maximum end
- Inner markers: (1-P)th percentile start to Pth percentile end
- Arrows show dependency relationships
- Branch outcomes create parallel sub-diagrams

## 9. History System

### 9.1 History Event Tracking

Every change creates a history event:
- User actions (node edits, deletions, additions)
- Simulations (with execution time)
- Parameter changes

Each event records:
- Timestamp
- Duration (for extended operations)
- Changed data
- Previous state (for undo)

### 9.2 Branching History

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

### 9.3 Reproducibility

**Simulation Storage**:
- Simulations store complete results (all sample events and outcomes), NOT just RNG seeds
- This representation does not require random number generation to "hydrate" the simulation
- Reloading a simulation from history uses the stored results directly
- No regeneration needed
- Ensures reproducibility even if simulation algorithm changes across software versions
- This is critical: changing the simulation implementation should not change historical simulation results

**DAG Snapshots**:
- Simulations reference a specific DAG version from when they were created
- Deleted nodes are preserved in the persistent object store
- References in simulations point to node versions as they existed at simulation time
- This ensures simulations remain valid even after nodes are deleted or modified

## 10. Implementation Considerations

### 10.1 Technology Stack

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

**Fuzzy Matching**: RapidFuzz for search functionality in list display mode

### 10.2 Code Quality Standards

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

### 10.3 Architecture Recommendations

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

## 11. Future Improvements

These features are planned but not part of the initial implementation:

### 11.1 Jira Integration

- Use past performance to constrain variance of task lengths
- Allow Jira plan updates as project plan updates
- Update timeline as tasks finish
- Discover new tasks from Jira
- Estimate costs of adding new tasks using history
- Associate tasks/branches with Jira issues
- Store metadata that doesn't map to Jira fields in attachments

### 11.2 Enhanced Task Features

- Review time and potential reviewers
- Worker affinities (different workers take different amounts of time)

### 11.3 Calendar Enhancements

- Holidays
- Vacations
- Sick days
- Custom work schedules

### 11.4 Enhanced Sampling

- Sample until all possible worlds happen at least K times
- Use pymc for sampling (enables oversampling rare worlds while keeping probabilities correct)

### 11.5 Visualization Enhancements

- Interactive hiding/showing of sub-tasks in Gantt charts
- Additional visualization types

## 12. Glossary

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
