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
  allowed_workers: optional list of worker ids  # Dual semantics based on task type:
                                                # - Parent tasks: defines the worker pool inherited by
                                                #   descendants (unless they override with their own list)
                                                # - Leaf tasks: the actual constraint on assignable workers
                                                # If absent, inherited from nearest ancestor with a list set,
                                                # or all workers if no ancestor has one (see Section 7.2).
  excluded_worker_tasks: list of task ids whose assignees cannot be assigned to this task

  # Completion tracking (see Section 3.1.1)
  completion: TaskCompletion
}
```

#### 3.1.1 Task Completion Schema

Task completion is modeled as a discriminated union of three states:

```
TaskCompletion = NotStartedCompletion | StartedCompletion | DoneCompletion

NotStartedCompletion {
  status: "not_started"  # discriminator
}

StartedCompletion {
  status: "started"  # discriminator
  assignee: worker id
  start_time: datetime  # when work began (for Gantt charts)
  hours_logged: float  # work-hours spent so far
}

DoneCompletion {
  status: "done"  # discriminator
  assignee: worker id | None  #If assignee was not recorded
  start_time: datetime  # when work began
  hours_logged: float  # total work-hours spent
  end_time: datetime  # when work finished (for Gantt charts)
}
```

**Design Rationale**:
- `hours_logged` tracks actual work-hours spent, independent of calendar time elapsed since `start_time`
- In real projects, work is done in pieces over multiple days, so elapsed calendar time does not equal work time
- `start_time` and `end_time` are for visualization (Gantt charts of historical/actual work), not for simulation logic
- The simulation uses `hours_logged` directly for rejection sampling (reject sampled durations < hours_logged)
- `DoneCompletion` fields are mutable: tasks can be reopened, hours corrected, etc.

#### 3.1.2 Legacy Task Completion Schema (Version 1.0)

The following schema was used in file format version 1.0 and must be migrated:

```
# Version 1.0 completion fields (DEPRECATED - migrate to TaskCompletion)
Task {
  ...
  # Task is done if actual_duration is present
  # actual_assignee and actual_start_time must be set together (task in progress or done)
  # actual_duration can only be set if actual_start_time is set
  actual_start_time: optional datetime
  actual_assignee: optional worker id
  actual_duration: optional float (work-hours)
}
```

See Section 4.4.1 for migration logic.

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

### 3.3 Dependency Graph Structure and Cycle Detection

The dependency graph is **endpoint-based**, not node-based. This means that each task or branch contributes multiple nodes to the dependency graph, rather than being treated as a single node.

#### 3.3.1 Endpoint Nodes

Each task **T** has two endpoint nodes in the dependency graph:
- **T.start** - When the task begins
- **T.end** - When the task completes

Each branch **B** has W+1 endpoint nodes (where W is the number of possible worlds):
- **B.occurrence** - When the branch condition is resolved
- **B.pw1, B.pw2, ..., B.pwW** - One node for each possible world

#### 3.3.2 Implicit Dependencies

For each task T, there is an implicit dependency:
- **T.end >= T.start** (a task must end after it starts)

This creates a directed edge: **T.start → T.end** in the precedence graph.

For each branch B with possible worlds pw1, pw2, ..., pwW, there are implicit dependencies:
- **pw1 >= B.occurrence**
- **pw2 >= B.occurrence**
- ...
- **pwW >= B.occurrence**

These create directed edges: **B.occurrence → B.pw1**, **B.occurrence → B.pw2**, etc.

#### 3.3.3 Explicit Dependencies

An explicit dependency defined on node N:
```
{
  source_endpoint: E1
  target_node_id: M
  target_endpoint: E2
  constraint_type: ">=" | "="
}
```

Means: **N.E1 >= M.E2** (N's endpoint E1 must occur at or after M's endpoint E2)

This creates a directed edge in the precedence graph: **M.E2 → N.E1**

#### 3.3.4 Cycle Detection

A cycle exists if there is a path in the directed graph that returns to its starting node. For example:

**Valid (no cycle)**:
- Task1.end >= Task2.start (Task1 must finish before Task2 starts)
- Task2.end >= Task1.start (Task1 must start before Task2 ends)
- Graph edges: Task2.start → Task1.end and Task1.start → Task2.end
- No cycle: These constraints can be satisfied (e.g., Task1: 0→10, Task2: 5→15)

**Invalid (cycle)**:
- Task1.end >= Task2.start
- Task2.start >= Task1.end
- Graph edges: Task2.start → Task1.end → Task2.start
- Cycle detected: Task2.start → Task1.end → Task2.start forms a loop

**Parent-Child Example (valid)**:
- Parent P with child C
- C.start >= P.start (child starts after parent)
- P.end >= C.end (parent ends after child)
- Graph edges:
  - P.start → P.end (implicit)
  - C.start → C.end (implicit)
  - P.start → C.start (from first dependency)
  - C.end → P.end (from second dependency)
- Complete path: P.start → C.start → C.end → P.end
- No cycle: This forms a chain, not a loop

#### 3.3.5 Visualization Implications

In the DAG visualization, dependency edges should ideally connect to the appropriate side of node boxes:
- Dependencies targeting the **start** endpoint connect to the left side of a task box
- Dependencies targeting the **end** endpoint connect to the right side of a task box
- Dependencies involving a branch's **occurrence** point connect to the branch decision point
- Dependencies targeting a specific **possible world** connect to the right side of that world's box

### 3.4 Worker Schema

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

### 3.5 Duration Distribution Schemas

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

### 3.6 DAG and History Schemas

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

**Version String**: Saved in file as `"version": "1.0"` (or current version)

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

#### 4.4.1 Migration: Version 1.0 to 1.1

**Task Completion Migration**:

Version 1.0 used three optional fields for completion tracking. Version 1.1 uses a discriminated union (`TaskCompletion`).

Migration rules:
1. **No completion fields set** → `NotStartedCompletion`
2. **actual_start_time + actual_assignee set, no actual_duration** → `StartedCompletion`
   - `assignee` = actual_assignee
   - `start_time` = actual_start_time
   - `hours_logged` = (migration_datetime - actual_start_time) / assignee.hours_per_workday
3. **All three fields set** → `DoneCompletion`
   - `assignee` = actual_assignee
   - `start_time` = actual_start_time
   - `hours_logged` = actual_duration
   - `end_time` = calculated from start_time + duration using calendar logic

**Note**: The `hours_logged` calculation for in-progress tasks (case 2) is an estimate based on elapsed calendar time. Users should verify and correct this value after migration if they have more accurate data.

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
- List of all selectable nodes:
  - Task nodes (with titles)
  - Branch decision points (occurrence points, labeled with branch title)
  - Branch possible worlds (labeled with possible world title, showing parent branch)
- Search bar to filter nodes using fuzzy matching (RapidFuzz library)
  - Nodes ranked by match quality

**Interaction**:
- Clicking a node switches back to DAG display with the node centered
  - Exception: When in select-target-node mode, clicking selects it as dependency target

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
  - Unified field with dual semantics (see Section 7.2):
    - For parent tasks: defines the worker pool inherited by descendants
    - For leaf tasks: the actual constraint on who can be assigned
  - Display states:
    - If empty and no ancestor has a list: "All workers (click to restrict)"
    - If empty and ancestor has a list: "Inherited from {ancestor name}: {worker list}" (read-only display, click to override)
    - If populated: Editable list with + button to add, trashcan to remove
- **Excluded Assignees**:
  - List of tasks whose assignees cannot be assigned here
  - **Add Task** button enters "select-task-node mode" (see Section 5.3.4)
  - Trashcan to remove

**Subtask Management** (leaf tasks):
- **Convert to Parent** button: Adds first child and navigates to it

**Subtask Management** (child tasks):
- **Add Sibling** button: Creates a new sibling task (child of same parent)

**Completion Tracking**:
- **Not Started** (default state): Shows "Start Task" button
- **Start Task** section (when starting):
  - Assignee dropdown (from project workers)
  - Start time datetime picker
  - Hours logged input (default 0 for new starts)
  - Creates `StartedCompletion`
- **In Progress** state: Shows current assignee, start time, hours logged (editable)
  - "Complete Task" button to finish
  - "Become not started" button → clears to `NotStartedCompletion`
- **Complete Task** section (when completing):
  - Hours logged input (carries over from started state, editable)
  - End time datetime picker
  - Creates `DoneCompletion`
- **Done** state: Shows all completion info (editable)
  - "Reopen Task" button → converts back to `StartedCompletion` (removes end_time)

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

Used when adding excluded assignee tasks. Activated when user clicks "Add Task" in the Excluded Assignees section.

Behavior:
- Similar to select-target-node mode but only task nodes are selectable (branches/possible worlds are not valid targets)
- Status bar or visual indicator shows "Select a task to exclude..."
- User navigates DAG (or list view) and clicks on a task node
- If task lacks required dependency (this_task.start >= excluded_task.start), user is prompted to add it automatically
- **Cancel** button or Escape key aborts selection mode
- Other editing and DAG modifications are disabled during selection

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

**Allowed Workers Resolution** (computed ephemerally at simulation start):
- Each task has an optional `allowed_workers` list with unified semantics:
  - For parent tasks: defines the worker pool inherited by descendants
  - For leaf tasks: the actual constraint on who can be assigned
- For tasks without an explicit `allowed_workers` list, the effective allowed workers are determined by walking up the ancestor chain:
  - Find the nearest ancestor with an `allowed_workers` list set
  - Use that list as the effective allowed workers for this task
  - If no ancestor has a list set, all workers are allowed
- This resolution happens once at simulation start; the computed values are not stored on the Task
- On sync/update from Jira: workers are added to `allowed_workers` but never removed, preserving manually-added workers

**Tasks in Progress**:
- A task with `StartedCompletion` is in progress
- During simulation, the task must:
  - Be assigned to the `completion.assignee` (not a random worker)
  - Use rejection sampling for duration: sample from distribution and reject durations < `hours_logged`
  - `hours_logged` is the actual work-hours spent so far, tracked independently of calendar time
  - This ensures the simulated duration is consistent with the task already being in progress
- **Note**: Unlike calendar-based elapsed time, `hours_logged` directly represents work done. This avoids issues where tasks worked on sporadically over many calendar days would appear to be near the extreme end of their duration distribution.

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

**Visual Organization**:

Task variants are grouped and sorted by their possible world sequence (the combination of branch outcomes that led to each variant):

1. **Grouping**: Variants are grouped by world sequence
2. **Sorting**: Groups are sorted by the start time of the first branch in each sequence
   - The base world (no branch outcomes) appears first
   - Within each world sequence, variants are sorted by task start time
3. **Dividers**: Horizontal lines separate groups of different world sequences
   - Makes it easy to see which tasks belong to each possible timeline

This organization helps readers understand which tasks execute together in each possible future.

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
   - The horizontal axis represents time. The placement
     on the timeline tells when that part of the task is likely to occur.
3. Draw dependency arrows:
   - Equality: double-ended arrow
   - Greater-than-or-equal: arrow from earlier to later (in time)
4. Each task has a fraction to indicate what fraction of samples it occurred in.

**Visual Encoding**:
- Box represents task temporal uncertainty
- Outer boundaries: minimum start to maximum end
- Inner markers: (1-P)th percentile start to Pth percentile end
- Arrows show dependency relationships
- Branch outcomes are implicit in the occurrence fraction.
- Branch nodes are not shown in the probabilistic timeline; their outcomes are revealed through the occurrence fractions of tasks that depend on them.

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

## 11. Jira Integration

### 11.1 Overview

Project Fluxx integrates with Jira Data Center to import epics and their issues, enabling data-driven duration estimation based on historical ticket completion data.

**Core Workflow**:
1. User imports an epic by key (e.g., FHIR-1234) via File menu
2. System creates a root task representing the epic
3. All issues in the epic become subtasks with proper hierarchy
4. Duration distributions are derived from historical project data
5. Workers are imported based on who logged work on epic tasks
6. User can hit "Update from Jira" to sync changes

### 11.2 Configuration and Authentication

**Server Configuration**:
- Each `.fluxx` file supports at most one Jira server
- Server URL stored in the project file
- On first import, user is prompted for the server URL
- Server URL cannot be changed after initial configuration (migration path for future)

**Authentication**:
- Personal Access Token (PAT) only
- Token is NOT stored in the `.fluxx` file
- Token is read from: `~/.local/share/secrets/<host>[.<port>]/<path>/personal_access_token.txt`
  - Example: For `https://jira.example.com:8443/jira`, token at `~/.local/share/secrets/jira.example.com.8443/jira/personal_access_token.txt`
- Reuses token path derivation from `fluxx.jql` module (factor out for shared use)

**Rate Limiting**:
- Default: 1 request per second
- User-configurable via import dialog
- Implemented using `requests_ratelimiter` library

**Retry Logic**:
- Exponential backoff on failures
- Maximum retry interval: 10 minutes
- Retries on transient errors (5xx, timeouts, connection errors)

### 11.3 Data Model Extensions

#### 11.3.1 Jira Reference Schema

```
ProjectKey: string # Matching [A-Z0-9_]{2,}

JiraIssueKey { # e.g., "FHIR-1234"
  project_key: ProjectKey

  issue_number: int
}

JiraReference {
  server_url: string  # Base URL of the Jira server
  issue_key: JiraIssueKey   # e.g., "FHIR-1234"
}
```

JiraIssueKey has a validator that it is of the form letters-numbers and is treated for type safety.

Added to Task schema:
```
Task {
  ...
  jira_reference: optional JiraReference  # Link to Jira issue
  jira_issue_type: optional string  # e.g., "Story", "Bug", "Task"
}
```

#### 11.3.2 Worker Jira Reference

```
Worker {
  ...
  jira_account_id: optional string  # Jira user account ID - default to None when upgrading
}
```

#### 11.3.3 Jira Duration Distribution

New distribution type for Jira-imported tasks:

```
JiraDurationDistribution(DurationDistribution) {
  original_estimate_seconds: optional int  # timetracking.originalEstimateSeconds
  story_points: optional float  # customfield_10473
  remaining_estimate_seconds: optional int  # timetracking.remainingEstimateSeconds
}
```

#### 11.3.4 Historical Duration Data

Stored in the project file for distribution fitting:

```
JiraDurationHistoryEntry {
  server_url: string
  issue_key: JiraIssueKey  # For deduplication on update
  original_estimate_seconds: optional int
  worker_jira_id: optional string
  issue_type: string
  total_logged_time_seconds: optional int
}

JiraSyncMetadata {
  server_url: string
  last_history_sync: datetime
  history_entries: list of JiraDurationHistoryEntry
}
```

**Sync Behavior Notes**:
- The set of Jira project keys to sync is derived dynamically by iterating over all tasks with `jira_reference` and collecting the distinct `project_key` values. This is effectively instant even for large files (<100K issues).
- A single `last_history_sync` timestamp is shared across all projects. When "Update from Jira" runs, historical data for all referenced projects is refreshed. This ensures the duration estimation model always uses globally up-to-date data.
- Only tasks with an explicit `jira_reference` are synchronized. Parent tasks are synced if they have a linked issue, but sibling epics under the same strategic release are not automatically included unless they too have linked issues.
- If per-project sync timestamps are ever needed, migration is straightforward: duplicate the single timestamp for each project.

#### 11.3.5 Project-Level Jira Configuration

```
ProjectFile {
  ...
  jira_config: optional {
    server_url: string
    sync_metadata: JiraSyncMetadata  # sync state
  }
}
```

### 11.4 Epic Import Process

#### 11.4.1 Import Dialog

Accessed via **File → Import from Jira...**

**First-time setup** (no server configured):
1. Prompt for Jira server URL
2. Validate URL format
3. Test authentication (verify PAT exists and works)
4. Store server URL in project file

**Import form**:
- Epic key input (e.g., "FHIR-1234")
- Rate limit setting (requests/second, default: 1)
- Import button

**Progress display** (modal):
- Current operation description
- Progress bar (when determinable)
- Cancel button
- Error display with retry option

#### 11.4.2 Issue Fetching

**API Endpoints Used**:
- `GET {path}/rest/api/2/search` - Query issues in epic
- `GET {path}/rest/api/2/issue/{key}` - Get issue details (if needed)

**JQL Queries**:
```
# Get all issues in epic
"Epic Link" = {epic_key} OR parent = {epic_key}

# Get historical data for distribution fitting (all completed issues in project)
project = {project_key} AND resolution in ("Complete", "Fixed", "Not a bug", "Done", "Cannot Reproduce") AND updated >= "{last_sync_date}"
```

**Fields to Request**:
- `key`, `summary`, `description`
- `issuetype` (for issue_type)
- `parent` (for hierarchy)
- `issuelinks` (for dependencies and hierarchy)
- `timetracking` (originalEstimateSeconds, remainingEstimateSeconds, timeSpentSeconds)
- `customfield_10473` (Story Points)
- `assignee` (for worker constraints on unstarted tasks or assignees on started/completed task)
- `resolution`, `resolutiondate` (for completion detection)
- `worklog` (for start detection and worker import)
- `status` (for completion detection and future intermediate statuses)

**Note on `names` expansion**: During development/debugging, include `expand=names` to see human-readable custom field names. This adds ~5KB per issue (~20% overhead) and should be disabled in production.

#### 11.4.3 Hierarchy Mapping

**Parent-Child Relationships**:
- Issues with `parent` field set become subtasks of the parent issue
- Epic becomes root task
- Standard Jira subtasks map to Project Fluxx subtasks
- "parent of"/"child of" link types also establish hierarchy

**Sub-epic Detection**:
- If an issue within the epic has `issuetype.name == "Epic"`, display warning:
  - "Warning: Issue {key} is a sub-epic. Sub-epics are not fully supported. It will be imported as a regular task."

#### 11.4.4 Dependency Mapping

**Jira Link Types → Project Fluxx Dependencies**:
- A "depends on" B / B "depended on by" A → `A.start >= B.end`
- A "schedule after" B / B "schedule before" A → `A.start >= B.end`

**Special Case - Both Tasks Started**:
When both linked tasks for a "depends on" or "schedule after" relationship have work logged (both are "started"):
- Remove the dependency from the import
- Rationale: This typically represents work moving to review phase, which we don't model yet

#### 11.4.5 Deduplication on Update

When syncing/updating:
- Match issues by `(server_url, issue_key)` tuple
- If task with matching `jira_reference` exists:
  - Update fields (summary→title, description, issue_type, etc.)
  - Update completion status
  - Update dependencies (respecting the "both started" rule)
- If no match: create new task

### 11.5 Duration Distribution Fitting

#### 11.5.1 Historical Data Collection

**Data Source**: All completed issues in the project containing the epic

**Completion Criteria**: `resolution.name` in:
- "Complete"
- "Fixed"
- "Not a bug"
- "Done"
- "Cannot Reproduce"

**Data Recorded Per Issue**:
```python
(
    original_estimate_seconds,  # or None
    worker_jira_id,
    issue_type,
    total_logged_time_seconds,  # or None
)
```

**Multi-worker Issues**: If multiple workers logged time on an issue, create one entry per worker, each with the total logged time. This is intentionally duplicative for initial implementation.

**Incremental Sync**: A single `last_history_sync` timestamp tracks when history was last fetched. On subsequent syncs, query only issues with `updated >= last_sync_date` for all referenced projects (see Section 11.3.4 for sync behavior details). The first sync when adding any new project will sync all its issues.

#### 11.5.2 Bin-Based Distribution Fitting (MVP Algorithm)

**Step 1: Fallback Distribution**
- Collect all `total_logged_time_seconds` values from completed issues
- Fit a shifted lognormal distribution to this data
- Use as fallback when original estimate is missing

**Step 2: Estimate-Based Binning**
- Minimum samples per bin: X = 30
- Work in log-space for all binning operations

**Algorithm**:
1. Sort all completed issues by `log(original_estimate_seconds)`
2. For each unique original estimate value E:
   a. Create initial symmetric bin (in log-space) around E, wide enough to contain X or more samples
   b. Set lower bound = midpoint between lowest included sample and next lower excluded sample
   c. Set upper bound = midpoint between highest included sample and next higher excluded sample
   d. Lowest bins (containing the minimum estimate) have lower bound = 0
   e. Highest bins (containing the maximum estimate) have upper bound = ∞
3. If total samples < X, create single bin covering all data
4. Fit shifted lognormal to `total_logged_time_seconds` within each bin

**At Simulation Time**:
- Run algorithm
- For task with original estimate E:
  - Find bin whose center is closest to E
  - Sample from that bin's fitted lognormal distribution
- For task with no original estimate:
  - Sample from fallback distribution

#### 11.5.3 Future: Improved Bayesian Model (Design Notes)

Use PyMC with a Bayesian Hierarchical model:

log(duration) ~ Normal(μ, σ)

μ = α_base + α_worker[w] + α_task_type[t] + f(log(estimate))
σ = σ_base + σ_worker[w] + σ_task_type[t] + g(log(estimate))

Where f and g are linear or spline functions (we can see what makes sense when we get to this phase and we know what the data distribution looks like.) And the α and σ terms are random variables.

**Input Features**:
- One-hot encoded issue type
- One-hot encoded worker ID
- log(original_estimate)

**Output**: log(total_logged_time)

Implement using PyMC (latest version). Use standard Bayesian operations to deal with missingness.

*Benefits*
Better handling of sparse data. Predictions better model the distribution.

*Testing*

At this point, we will have quite a bit of real data. Before we start implementing, we should segment out a randomly-selected test set (30%) of tickets, which we will use for a final decision as to what method to use in the final product. We will also separate out a 30% validation set we can use to validate our test procedures and use for other consequential decisions. The remaining 40% of our data is a test set that we can use however we want.

We will consider several methods: for example, the rough histogram binning method, baseline simple-as-possible predict/sample-from-closest (making sure we aren't being too complicated), Bayesian with linear elements, or Bayesian with spline. We'll decide what ones to implement when we get there.
As part of engineering, we may do some calibration plots (predicted quantiles vs observed frequencies) for the models to understand how they are wrong - are they systematically over or under-estimating part of the data.

Final decision:
* Train all selected estimation methods on training + validation set.
* Choose the model that assigns the highest probability to the test set.
* Also do some calibration plots (see above) for a more subjective decision criterion. For example, if two models are similar but one has a superior calibration plot, we may choose the model with slightly lower probability if it's significantly better calibrated.

### 11.6 Worker Import

#### 11.6.1 Import Criteria

We import all workers who have logged time or been assigned an issue in the project we import from.

**Allowed Workers List Population**:
- If a worker logged work on an epic, add the worker to the `allowed_workers` list for the epic task
- The epic's `allowed_workers` list is inherited by all its descendants (unless they override with their own list—see Section 7.2 for resolution semantics)
- On sync/update: workers are added to `allowed_workers` but never removed
  - This preserves manually-added workers (useful when planning ahead with workers who haven't yet logged time on the epic)

**Rationale**: The broad worker import (project-wide, not just epic-scoped) provides historical data for duration estimation. The `allowed_workers` mechanism on parent tasks distinguishes which workers are expected to work on a specific epic, since personnel shift over time.

#### 11.6.2 Productivity Calculation

**Days Counted**: Only days on which the worker logged at least one worklog entry on any issue in any epic within the current `.fluxx` model.

**Calculation**:
1. For each day the worker logged work:
   - Sum all time logged that day (across all issues in imported epics)
2. `hours_per_workday` = average of daily logged hours

If the worker logged no work, assign them the average of all daily logged hours for all workers. It's not a good estimate (they are clearly from a different distribution), but it gives us a number to stick in the box.

**Deduplication**: Match workers by `jira_account_id`. Update existing worker's productivity on sync.

### 11.7 Task Completion Mapping

#### 11.7.1 Not Started

A task is "not started" if:
- No worklog entries exist

**Assignee Handling**:
- If issue has an assignee but no work logged:
  - Set `allowed_workers` to only that assignee (constraint, not started status)

#### 11.7.2 Started

A task is "started" if:
- Has worklog entries
- Resolution is not set (or not in completed list)

**Mapping**:
```python
StartedCompletion(
    assignee=jira_assignee_field or author_with_most_worklogs,
    start_time=first_worklog_date,
    hours_logged=sum(worklog.timeSpentSeconds) / 3600,
)
```

#### 11.7.3 Done

A task is "done" if:
- Has a completed resolution

**With Work Logged**:
```python
DoneCompletion(
    assignee=jira_assignee_field if present else author_with_most_worklogs,
    start_time=first_worklog_date,
    hours_logged=sum(worklog.timeSpentSeconds) / 3600,
    end_time=last_worklog_date,
)
```

**Rationale for `last_worklog_date` as `end_time`**: In practice, tickets often receive little attention after work is complete—the resolution date may lag significantly behind when work actually finished. The last worklog entry is the best available signal of when substantive work ended. Occasionally the last worklog date falls after the resolution date (e.g., "just one little fix" logged retroactively); this is acceptable. This choice may be revisited or made configurable in the future; configurability would require a mechanism to preserve the setting across Jira updates.

**Without Work Logged** (closed with no work):
```python
DoneCompletion(
    assignee=assignee,
    start_time=issue_created_date,  # Best approximation
    hours_logged=1e-6,  # See Section 11.7.4
    end_time=resolution_date,
)
```

#### 11.7.4 Zero-Work Completed Tasks

**Issue**: Tasks closed without logged work need a `hours_logged` value.

**Investigation Required**: Before implementation, analyze whether `NaN` could be used safely:
- Check all calculations that use `hours_logged`
- Verify NaN propagation doesn't break simulation
- Document findings

**Initial Approach**: Use `1e-6` (effectively zero but numeric) until investigation complete.

### 11.8 Linking Existing Tasks to Jira

Users can link a manually-created task to a Jira issue after the fact.

**Prerequisite**: A Jira server must already be configured (via a prior "Import from Jira" operation). If no server is configured, the Jira Issue field displays an error: "No Jira server configured. Use File → Import from Jira to configure."

**Expected Workflow**: Typically, users create an epic in Jira first, then import it to start a Jira-linked `.fluxx` file. Manual linking is for cases where a task was planned in Project Fluxx before the corresponding Jira issue existed.

**UI Flow**:
1. In Task Editor, there is a Jira Issue field. Displays `<enter issue key>` prompt when `jira_reference` is None. The field is editable when already set.
2. On loss of focus (after user enters/changes the key):
   a. **Invalid key**: Display warning, revert field to previous value.
   b. **Valid key, no unsaved changes**: Load issue data from Jira, creating a new undo point. User can undo to recover previous values.
   c. **Valid key, unsaved changes exist**: Save current changes first (creating a new history revision), then load issue data from Jira, creating another undo point.
3. On subsequent "Update from Jira", the linked task will be synced.

**Field Overwrite Warning**: If the user edits fields that are synced from Jira (title, description, etc.) and then clicks Apply, display a warning dialog:
> "WARNING: Your changes to fields {list of changed synced fields} will be overwritten next time you sync with Jira." [OK]

This ensures users understand that local edits to Jira-synced fields are temporary.

### 11.9 "Become Child Of" Feature

A general-purpose feature to reparent any task (not just Jira-imported ones).

#### 11.9.1 UI

**Location**: Task Editor panel, button labeled "Become Child Of..."

**Flow**:
1. Click button
2. Enter select-task-node mode (similar to dependency selection)
3. Select target parent task
4. System validates and executes reparenting

#### 11.9.2 Validation

**Automatic Changes**:
- Remove existing parent-child dependencies (from old parent, if any)
- Add new parent-child dependencies:
  - `child.start >= new_parent.start`
  - `new_parent.end >= child.end`
- If new parent was a leaf task, convert it to parent (remove duration distribution)

**Conflict Detection**:
Check if existing explicit dependencies conflict with new parent-child relationship:
- Would create a cycle
- Violate temporal constraints

**On Conflict**:
- Display dialog listing conflicting dependencies
- "The following dependencies conflict with making this task a child of {parent}:"
  - List each conflict with explanation
- Ensure task is now unchanged.
- The user must manually resolve conflicts via the rest of the UI.

### 11.10 Menu Structure

```
File
├── ...
├── ───────────
├── Import from Jira...
├── Update from Jira        (enabled when jira_config exists)
├── ───────────
├── ...
```

### 11.11 Error Handling

**Authentication Errors**:
- Token not found: "Personal access token not found at {path}. Please create the file with your Jira PAT."
- Token invalid: "Authentication failed. Please verify your personal access token at {path}."

**Network Errors**:
- Retry with exponential backoff (max 10 minutes)
- After max retries: "Failed to connect to Jira after multiple attempts. Check your network connection."
- The user can abort early in the progress bar display.

**Rate Limiting (429 responses)**:
- Honor `Retry-After` header if present
- Otherwise use exponential backoff

**Issue Not Found**:
- "Issue {key} not found on {server}. Please verify the issue key."

### 11.12 Implementation Notes

**Dependencies**:
- `requests` - HTTP client (already used)
- `requests_ratelimiter` - Rate limiting
- `tenacity` or custom - Retry logic with exponential backoff

**Code Organization**:
```
fluxx/
├── jira/
│   ├── __init__.py
│   ├── client.py      # Jira REST API client with rate limiting
│   ├── auth.py        # Token management (factored from jql.py)
│   ├── import.py      # Epic import logic
│   ├── sync.py        # Update/sync logic
│   ├── mapping.py     # Jira → Project Fluxx data mapping
│   └── distributions.py  # Bin-based distribution fitting
```

**Testing**:
- Mock Jira API responses for unit tests
- Integration tests against test Jira instance (optional, manual)

## 12. Future Improvements

These features are planned but not part of the initial implementation:

### 12.1 Jira Integration Enhancements

#### 12.1.1 Configurable Resolution Names
- Allow user to configure which resolution names indicate completion
- Current hardcoded list: "Complete", "Fixed", "Not a bug", "Done", "Cannot Reproduce"

#### 12.1.2 Configurable Dependency Link Types
- Allow user to configure which Jira link types map to dependencies
- Current hardcoded list: "depends on"/"depended on by", "schedule after"/"schedule before"

#### 12.1.3 Configurable Custom Fields
- Allow mapping of custom field IDs for:
  - Story Points (currently `customfield_10473`)
  - Any additional fields that may be useful

#### 12.1.4 Strategic Releases and Initiatives
- Support for "Strategic Releases" (parents of epics) from Jira Portfolio Plan
- Support for "Initiatives" (parents of strategic releases)
- Full hierarchy: Initiative → Strategic Release → Epic → Story/Task → Subtask
  (the "parent of"/"child of" links allow unlimited nesting)

#### 12.1.5 Multiple Server Support
- Allow a single `.fluxx` file to reference multiple Jira servers
- Migration path from single-server model

#### 12.1.6 Hierarchical Bayesian Duration Model
- Replace bin-based fitting with Hierarchical Bayesian Duration Model
- See design notes in section 11.5.3

#### 12.1.7 Enhanced Duration Estimation with In-Progress Data
- Include remaining estimate and/or total time logged for non-completed tasks in model
- Reduces need for rejection sampling during simulation and more accurately reflects knowledge

#### 12.1.8 Worker Productivity Distribution
- Replace single `hours_per_workday` with a distribution
- Derive from historical worklog patterns per worker
- Account for variability in daily productivity

#### 12.1.9 Review Phase Modeling
- Model the "under review" phase for tasks.
- Better model the actual workflow for many issues.
- Better utilizes when both a reviewer and a developer log time on a task.
- Better handling of dependencies when both tasks are in progress

#### 12.1.10 Multi-Worker Issue Handling
- More sophisticated handling when multiple workers log time on an issue
- Currently: duplicates entry for each worker with total time

### 12.2 Enhanced Task Features

- Review time and potential reviewers
- Worker affinities (different workers take different amounts of time)

### 12.3 Calendar Enhancements

- Holidays
- Vacations
- Sick days
- Custom work schedules

### 12.4 Enhanced Sampling

- Sample until all possible worlds happen at least K times
- Use pymc for sampling (enables oversampling rare worlds while keeping probabilities correct)

### 12.5 Visualization Enhancements

- Interactive hiding/showing of sub-tasks in Gantt charts
- Additional visualization types

## 13. Glossary

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
