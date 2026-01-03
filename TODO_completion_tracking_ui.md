# Completion Tracking - Implementation Todo

Prerequisite work for Jira integration: data model for task completion states, migration, simulation updates, and UI.

**Note**: Testing is done throughout (hooks check coverage). Each section includes its tests.

## 1. Data Model: Task Completion Types

Replace `actual_start_time`, `actual_assignee`, `actual_duration` fields with discriminated union:

- [x] Define `NotStartedCompletion` - no fields (just type discriminator)
- [x] Define `StartedCompletion`:
  - `assignee: WorkerId`
  - `start_time: datetime`
  - `hours_logged: float` (work-hours spent so far)
- [x] Define `DoneCompletion`:
  - `assignee: WorkerId`
  - `start_time: datetime`
  - `hours_logged: float` (total work-hours spent)
  - `end_time: datetime`
- [x] Define `TaskCompletion = NotStartedCompletion | StartedCompletion | DoneCompletion`
- [x] Update `Task` model: replace three optional fields with `completion: TaskCompletion`
- [x] Update `dag_operations.py` for new completion model
- [x] Update validation if needed
- [x] Tests for completion type model and transitions

## 2. Migration

- [x] Add file format version bump (1.0 -> 1.1)
- [x] Migration logic for old format:
  - No completion fields -> `NotStartedCompletion`
  - `actual_start_time` + `actual_assignee` without `actual_duration` -> `StartedCompletion`
    - `hours_logged = (migration_datetime - actual_start_time) / assignee.hours_per_workday`
  - All three fields present -> `DoneCompletion`
    - `hours_logged = actual_duration`
    - `end_time = actual_start_time + timedelta` (calculate from duration and hours_per_workday)
- [x] Tests for migration logic (all three cases)

## 3. Simulation Engine Updates

- [x] Update `sample_in_progress_task_remaining_duration()`:
  - Use `hours_logged` directly instead of calculating elapsed time from `start_time`
  - Rejection sampling: reject samples where `duration < hours_logged`
- [x] Update `SimulationEngine` to read from new completion model
- [x] Tests for simulation with in-progress tasks using new model
- [ ] Handle worker assigned to multiple in-progress tasks:
  - Worker splits time equally between all their assigned in-progress tasks
  - Worker cannot be assigned to any new tasks until their current in-progress tasks complete
  - (Future: priority-based allocation, explicit time splits)

## 4. Task Editor: Completion Tracking Section

- [x] Add "Start Task" section:
  - Assignee dropdown (from project workers)
  - Start time datetime picker
  - Hours logged input (default 0 for new starts)
- [x] Add "Complete Task" section (enabled when started):
  - Hours logged input (carries over from started state)
  - End time datetime picker
- [x] State transition buttons:
  - "Start Task" (NotStarted -> Started)
  - "Complete Task" (Started -> Done)
  - "Become not started" (Started -> NotStarted)
  - "Reopen Task" (Done -> Started)
- [x] Wire up to controller with new completion types
- [x] GUI tests for task editor completion section

## 5. Branch Editor: Resolution Section

- [ ] Add "Resolve Branch" section:
  - Dropdown listing all possible worlds
- [ ] Wire up to controller (`update_branch()` with `chosen_world_id`)
- [ ] GUI tests for branch editor resolution section

## 6. DAG View: Completion Status Indicators

- [ ] Task nodes show visual indicator for status:
  - NotStartedCompletion: default styling
  - StartedCompletion: distinct color/border (e.g., yellow border)
  - DoneCompletion: distinct color/icon (e.g., green with checkmark)
- [ ] Branch nodes show resolved state:
  - Unresolved: default styling
  - Resolved: show which world was chosen, gray out others
- [ ] GUI tests for DAG view status indicators

## 7. List View: Completion Status Display

- [ ] Add status indicator to list items:
  - Task items show [Not Started], [In Progress], or [Completed]
  - Branch items show [Unresolved] or [Resolved: <world>]
- [ ] Consider adding filter/sort by status
- [ ] GUI tests for list view status display

## 8. Controller Updates

- [x] Update `update_task()` for new completion model
- [ ] Add `update_branch()` support for `chosen_world_id`
- [x] Ensure undo/redo works for completion state changes
- [x] Tests for controller completion operations
