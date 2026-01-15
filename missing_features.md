# Missing Features

This document tracks features that were planned but not yet implemented.

---

## 1. CSV Export: `bin_centers` Column

**Source**: `TODO-improve-jira-duration-distribution.md`, Phase 8 (lines 189-204)

**Status**: Not implemented

### Description

The `--write-historical-data-csv` CLI export is missing a `bin_centers` column that would show which empirical bins each historical (estimate, actual) pair belongs to.

### Planned Specification

From the original plan:

```
CSV columns:
...
- bin_centers: Pipe-separated list of bin centers that contain this (estimate, actual) pair
```

> The `bin_centers` column helps analyze which historical data points inform each bin

### Implementation Notes

1. **Location**: `src/fluxx/__main__.py` in `write_historical_data_csv()`

2. **Algorithm**:
   - Build bins using `create_empirical_bins()` from `fluxx.jira.distributions`
   - For each history entry with an estimate, find all bins whose sample set contains this (estimate, actual) pair
   - Format as pipe-separated list of center values, e.g., `"1.0|2.0|4.0"`

3. **Edge cases**:
   - Entries without `original_estimate_seconds` won't appear in any bin (output empty string)
   - Entries without `total_logged_time_seconds` won't appear in any bin (output empty string)

4. **Example output**:
   ```csv
   issue_key,original_estimate_hours,total_logged_hours,bin_centers
   PROJ-1,1.0,1.5,"1.0|2.0"
   PROJ-2,4.0,3.5,"4.0"
   PROJ-3,,,""
   ```

5. **Dependencies**:
   - `from fluxx.jira.distributions import create_empirical_bins`
   - Need to convert history entries to (estimate_hours, actual_hours) tuples
   - Need to check membership in each bin's `samples` list

### Why It Was Deferred

The core empirical sampling functionality works correctly without this column. This is an exploratory data analysis (EDA) convenience feature that helps users understand how the binning algorithm groups their historical data. It does not affect simulation behavior.

---

## 2. DoneCompletion.assignee Optional

**Source**: `project_fluxx_specification.md`, Section 3.1.1

**Status**: Not implemented

### Description

The specification states that `DoneCompletion.assignee` should be `worker id | None` to handle cases where the assignee was not recorded. Currently, the field is required.

### Current State

In `src/fluxx/data/models.py` (line 379), `DoneCompletion.assignee` is defined as:
```python
assignee: WorkerId = Field(description="Worker who completed this task")
```

### Implementation Notes

- Change type from `WorkerId` to `WorkerId | None`
- Update serialization/deserialization to handle None
- Update simulation scheduler to handle unassigned completed tasks
- Update UI to show "(unrecorded)" when assignee is None

### Acceptance Criteria

- `DoneCompletion` can be created with `assignee=None`
- File format supports None assignee for completed tasks
- UI displays placeholder for unrecorded assignee

---

## 3. Dependency Edge Endpoint Visualization

**Source**: `project_fluxx_specification.md`, Section 3.3.5

**Status**: Not implemented

### Description

Dependency edges should connect to the appropriate side of node boxes:
- Dependencies targeting the **start** endpoint connect to the left side
- Dependencies targeting the **end** endpoint connect to the right side
- Dependencies targeting **occurrence point** connect to the branch decision point

### Current State

In `src/fluxx/gui/widgets/dag_view/dag_graphics_view.py`, edges always connect to the center of nodes using `source_item.pos()` and `target_item.pos()`, regardless of endpoint type.

### Implementation Notes

- Modify `EdgeItem` to accept source/target endpoints
- Calculate connection points based on endpoint type:
  - START: left center of node rectangle
  - END: right center of node rectangle
  - OCCURRENCE_POINT: center of branch node
- Update edge routing to avoid overlapping lines

### Acceptance Criteria

- Start-endpoint dependencies connect to left side of task boxes
- End-endpoint dependencies connect to right side of task boxes
- Branch dependencies connect appropriately to occurrence points

---

## 4. Auto-Save System

**Source**: `project_fluxx_specification.md`, Section 4.2

**Status**: Not implemented

### Description

The specification defines an auto-save system that:
- Auto-saves every 5 minutes (configurable)
- Saves to `.fluxx_autosave/<project_name>_autosave.fluxx`
- Preserves auto-save on crash, deletes on clean exit
- Uses atomic save (write to `.tmp` then rename)

### Current State

No auto-save functionality exists. Direct file writes are used without atomic operations.

### Implementation Notes

1. **Auto-save timer** in `MainWindow`:
   - QTimer with 5-minute interval
   - Configurable via settings
   - Triggers `_auto_save()` method

2. **Auto-save directory**:
   - Create `.fluxx_autosave/` in project directory
   - Clean up on normal exit via `closeEvent()`

3. **Atomic save** in `persistence.py`:
   ```python
   def save_project(project: ProjectFile, path: Path) -> None:
       temp_path = path.with_suffix(".tmp")
       with open(temp_path, "w") as f:
           json.dump(...)
       temp_path.rename(path)  # Atomic on POSIX
   ```

### Acceptance Criteria

- Project auto-saves every 5 minutes when modified
- Auto-save file preserved after crash
- Clean exit removes auto-save file
- Atomic save prevents file corruption

---

## 5. Auto-Save Recovery Prompt

**Source**: `project_fluxx_specification.md`, Section 4.3

**Status**: Not implemented

### Description

On startup, the application should check for auto-save files and prompt the user to recover:
- "Found auto-saved work from [time]. Recover?"
- Options: Recover, Discard, Open Both

### Current State

No recovery logic exists in `src/fluxx/__main__.py` or `MainWindow`.

### Implementation Notes

1. On startup, scan for `.fluxx_autosave/*.fluxx` files
2. Compare timestamps with corresponding project files
3. Show dialog with recovery options
4. Handle user choice accordingly

### Acceptance Criteria

- Startup detects auto-save files
- Dialog prompts for recovery action
- All three options (Recover/Discard/Open Both) work correctly

---

## 6. Recent Files Menu

**Source**: `project_fluxx_specification.md`, Section 4.3

**Status**: Not implemented

### Description

The File menu should show the 5 most recently opened projects for quick access.

### Current State

No recent files tracking or submenu in `src/fluxx/gui/main_window.py`.

### Implementation Notes

1. Store recent files in QSettings or config file
2. Add "Recent Files" submenu to File menu
3. Track file opens/saves to update list
4. Handle missing files gracefully (remove from list)

### Acceptance Criteria

- Recent Files submenu appears in File menu
- Shows up to 5 most recent projects
- Clicking a recent file opens it
- Missing files are removed from list

---

## 7. Backup Before Migration

**Source**: `project_fluxx_specification.md`, Section 4.4

**Status**: Not implemented

### Description

Before migrating a file to a newer version, create a backup: `<filename>.backup_v<old_version>`.

### Current State

Migration logic exists in `src/fluxx/data/migration.py` but no backup is created before applying migrations.

### Implementation Notes

1. In `load_project()`, before calling `apply_migrations()`:
   ```python
   if needs_migration:
       backup_path = path.with_suffix(f".backup_v{old_version}")
       shutil.copy2(path, backup_path)
   ```
2. Log backup creation to user

### Acceptance Criteria

- Opening an old-format file creates a backup
- Backup filename includes original version number
- Backup contains exact original file contents

---

## 8. Export Submenu

**Source**: `project_fluxx_specification.md`, Section 4.5

**Status**: Not implemented (CLI only for CSV)

### Description

File menu should have Export submenu with:
- Export to CSV
- Export Gantt Chart

### Current State

- CSV export exists only via CLI (`--write-historical-data-csv`)
- Gantt chart visualization exists but no export functionality
- No Export submenu in GUI

### Implementation Notes

1. Add Export submenu to File menu
2. "Export to CSV" opens file dialog, exports historical data
3. "Export Gantt Chart" opens file dialog, saves current Gantt as PNG/PDF

### Acceptance Criteria

- Export submenu appears in File menu
- CSV export works from GUI
- Gantt chart can be saved to image file

---

## 9. Default Worker on New Project

**Source**: `project_fluxx_specification.md`, Section 4.6

**Status**: Not implemented

### Description

When creating a new project, create a default worker "Worker 1" with 8 hours/day.

### Current State

`controller.new_project()` initializes with `workers=[]` (empty list).

### Implementation Notes

In `src/fluxx/gui/controller.py`, `new_project()`:
```python
default_worker = Worker(
    id=WorkerId(str(uuid4())),
    name="Worker 1",
    hours_per_workday=8.0,
)
project = ProjectFile(..., workers=[default_worker])
```

### Acceptance Criteria

- New projects have one worker named "Worker 1"
- Worker has 8 hours/day productivity
- User can edit/delete this worker

---

## 10. History Widget with Tree Navigation

**Source**: `project_fluxx_specification.md`, Section 5.2.1

**Status**: Partial (backend only)

### Description

The control bar should have a History Widget with:
- Display of current history state
- Dropdown for tree navigation
- Visual representation of history branches

### Current State

- Backend: Full tree structure in `src/fluxx/data/undo.py`
- UI: Only placeholder label "Current Version" in control_bar.py
- Linear undo/redo via menu works, but no tree visualization

### Implementation Notes

1. Replace label with dropdown/combo widget
2. Build tree model from `project.history_events`
3. Show event descriptions and timestamps
4. Allow navigation to any history node
5. Indicate current position and branches

### Acceptance Criteria

- History dropdown shows event tree
- User can navigate to any history state
- Branches are visually distinguishable
- Current position is highlighted

---

## 11. Collapsible Nodes in DAG View

**Source**: `project_fluxx_specification.md`, Section 5.2.2

**Status**: Not implemented

### Description

Task nodes with subtasks should be collapsible to hide their children.

### Current State

All nodes are always rendered in the DAG view. No collapse/expand functionality.

### Implementation Notes

1. Add expand/collapse state to node items
2. Add +/- button or double-click handler
3. When collapsed, hide child nodes and edges
4. Recalculate layout after collapse/expand

### Acceptance Criteria

- Parent nodes show collapse indicator
- Clicking collapses/expands children
- Layout updates appropriately
- Collapsed state persists during session

---

## 12. Assignee Exclusion Visualization

**Source**: `project_fluxx_specification.md`, Section 5.2.2

**Status**: Not implemented

### Description

Assignee exclusion relationships should be visualized with purple lines and a 🚫 symbol pointing to the excluded task.

### Current State

`excluded_worker_tasks` data model exists but is not rendered in the DAG view.

### Implementation Notes

1. Add new edge type for exclusion relationships
2. Style: purple color (#800080), dashed line, 🚫 symbol
3. Draw from excluding task to excluded task
4. Different visual from dependency arrows

### Acceptance Criteria

- Exclusion edges appear in DAG view
- Distinct purple styling with prohibition symbol
- Clear direction showing which task excludes which

---

## 13. Duration Distribution Preview

**Source**: `project_fluxx_specification.md`, Section 5.3.2

**Status**: Partial (parameters only)

### Description

Task editor should show a visualization/preview of the duration distribution (histogram or curve).

### Current State

Duration parameters can be edited but no visual preview of the distribution shape.

### Implementation Notes

1. Add matplotlib widget below distribution parameters
2. Render probability density function for current parameters
3. Update preview on parameter change
4. Show key statistics (mean, median, percentiles)

### Acceptance Criteria

- Distribution preview appears in task editor
- Preview updates as parameters change
- Shows shape of the distribution visually

---

## 14. Select-Task-Node Mode Visual Indicator

**Source**: `project_fluxx_specification.md`, Section 5.3.4

**Status**: Partial (mode exists, indicator missing)

### Description

When in select-task-node mode (for excluded assignees), show visual indicator: "Select a task to exclude..."

### Current State

Select mode exists with cursor change but no text indicator in status bar or UI.

### Implementation Notes

1. Add status label or tooltip during select mode
2. Show "Select a task to exclude..." message
3. Clear message when mode exits

### Acceptance Criteria

- Visual text indicator shown during select mode
- Clear instructions for user action
- Indicator disappears when mode exits

---

## 15. Persistent Validation Error Message

**Source**: `project_fluxx_specification.md`, Section 5.3.5

**Status**: Partial (dialogs only)

### Description

Editor should show persistent error message at top explaining validation issues and how to fix them.

### Current State

Errors are shown in modal dialogs but no persistent inline error display at top of editor.

### Implementation Notes

1. Add error label widget at top of editor panel
2. Update label with first validation error
3. Clear when issue is resolved
4. Red text with clear fix instructions

### Acceptance Criteria

- Error message visible at top of editor
- Explains the issue and fix
- Updates dynamically as user edits

---

## 16. Simulation Checkpointing During Execution

**Source**: `project_fluxx_specification.md`, Section 7.5

**Status**: Partial (model only)

### Description

During long-running simulations:
- Create checkpoints every 100 samples (configurable)
- Save completed samples, RNG state, timestamp

### Current State

- `Checkpoint` data model exists in `models.py`
- `Simulation.last_checkpoint` field exists
- No checkpoint creation logic in `SimulationEngine.run()`

### Implementation Notes

1. In simulation loop, check sample count against checkpoint interval
2. Serialize current state to `last_checkpoint`
3. Save project file with checkpoint data
4. Allow configuration of checkpoint interval

### Acceptance Criteria

- Checkpoints created periodically during simulation
- Checkpoint data persisted to file
- Configurable interval (default 100 samples)

---

## 17. Simulation Resume from Checkpoint

**Source**: `project_fluxx_specification.md`, Section 7.5

**Status**: Not implemented

### Description

- On app startup, check for incomplete simulations
- Prompt "Resume simulation with X/Y samples completed?"
- Restore RNG state and continue from last checkpoint

### Current State

No resume logic in startup code or simulation management UI.

### Implementation Notes

1. On project load, check for simulations with `status == RUNNING`
2. Show resume dialog with checkpoint information
3. Restore RNG state and continue from `completed_samples`
4. Add "Resume" button to simulation list UI

### Acceptance Criteria

- Incomplete simulations detected on project load
- User prompted to resume
- Simulation continues correctly from checkpoint

---

## 18. Parallel Simulation Execution

**Source**: `project_fluxx_specification.md`, Section 7.1

**Status**: Not implemented

### Description

Simulations should run with multiple parallel processes:
- Default: 2 × CPU count
- Configurable by user
- RNG state maintained per process

### Current State

`SimulationEngine` runs sequentially. Comment states "(not implemented yet)" for parallel execution.

### Implementation Notes

1. Use multiprocessing.Pool for parallel samples
2. Maintain separate RNG state per worker
3. Collect results and merge
4. Handle early termination across processes

### Acceptance Criteria

- Simulations use multiple CPU cores
- Significant speedup for large sample counts
- Results identical to sequential execution (deterministic)

---

## 19. Jira Rate Limit Setting in UI

**Source**: `project_fluxx_specification.md`, Section 11.4.1

**Status**: Partial (backend only)

### Description

Import dialog should have user-configurable rate limit setting (requests/second).

### Current State

- `JiraClient` accepts `rate_limit` parameter
- Import dialog uses hardcoded default (1 req/sec)
- No UI control for rate limit

### Implementation Notes

1. Add spinbox/slider for rate limit in import dialog
2. Pass configured value to JiraClient
3. Default: 1.0 req/sec, range: 0.1 - 10.0

### Acceptance Criteria

- Rate limit control visible in import dialog
- User can adjust rate limit
- Setting is respected during import

---

## 20. Import Cancel During Operation

**Source**: `project_fluxx_specification.md`, Section 11.4.1

**Status**: Partial (pre-import only)

### Description

Progress bar should have a cancel button that aborts an ongoing import.

### Current State

Cancel button cancels dialog setup but not an active import operation.

### Implementation Notes

1. Run import in background thread
2. Add cancellation token/flag
3. Check flag in import loop
4. Clean up partial import on cancel

### Acceptance Criteria

- Cancel button works during import
- Import stops gracefully
- Partial data cleaned up or preserved

---

## 21. Import Error Retry Option

**Source**: `project_fluxx_specification.md`, Section 11.4.1

**Status**: Partial (display only)

### Description

Error display should include retry option for failed imports.

### Current State

Errors are displayed but no automatic retry button.

### Implementation Notes

1. Add "Retry" button to error display
2. Clear error state and restart import
3. Maybe add retry count limit

### Acceptance Criteria

- Retry button appears after error
- Clicking retry restarts the import
- Works for network/transient errors

---

## 22. "schedule before" Link Type Support

**Source**: `project_fluxx_specification.md`, Section 11.4.4

**Status**: Partial

### Description

Both "schedule after" and "schedule before" Jira link types should map to dependencies.

### Current State

"schedule after" is implemented but "schedule before" is missing from BLOCKS_LINK_TYPES.

### Implementation Notes

In `src/fluxx/jira/extraction.py`, add to BLOCKS_LINK_TYPES:
```python
BLOCKS_LINK_TYPES = {"Blocks", "blocks", "is blocked by", "Schedule before", "schedule before"}
```

### Acceptance Criteria

- "schedule before" links create appropriate dependencies
- Dependency direction matches specification

---

## 23. "Become Child Of" Button

**Source**: `project_fluxx_specification.md`, Section 11.9

**Status**: Not implemented

### Description

Task editor should have "Become Child Of..." button that:
1. Enters select-task-node mode
2. User selects new parent task
3. System validates and executes reparenting

### Current State

No reparenting UI exists in task editor.

### Implementation Notes

1. Add "Become Child Of..." button to task editor
2. Implement select-parent mode (similar to dependency selection)
3. Validate: no cycles, no constraint violations
4. Update parent-child relationships and dependencies

### Acceptance Criteria

- Button appears in task editor
- Select mode works to choose parent
- Reparenting updates all relationships correctly

---

## 24. Reparenting Conflict Detection Dialog

**Source**: `project_fluxx_specification.md`, Section 11.9.2

**Status**: Not implemented

### Description

When reparenting would cause conflicts:
- Detect cycle creation or constraint violations
- Display dialog listing conflicts
- Let user resolve manually

### Current State

Feature depends on #23 which is not implemented.

### Implementation Notes

1. Before reparenting, check for:
   - Cycles in dependency graph
   - Temporal constraint violations
2. If conflicts, show dialog listing each conflict
3. Abort reparenting if conflicts exist

### Acceptance Criteria

- Conflicts detected before reparenting
- Clear explanation of each conflict
- User informed about how to resolve
