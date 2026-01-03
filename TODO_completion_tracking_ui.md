# Completion Tracking UI - Implementation Todo

Prerequisite work for Jira integration: UI for marking tasks as started/completed and resolving branches.

## Task Editor: Completion Tracking Section

- [ ] Add "Start Task" section to task editor
  - [ ] Assignee dropdown (from project workers)
  - [ ] Start time datetime picker
  - [ ] Validation: both must be set together
- [ ] Add "Complete Task" section to task editor
  - [ ] Duration input field (work-hours)
  - [ ] Only enabled when task is started (has actual_start_time)
  - [ ] Setting duration marks task as done
- [ ] Wire up to controller `update_task()` with actual_start_time, actual_assignee, actual_duration

## Branch Editor: Resolution Section

- [ ] Add "Resolve Branch" section to branch editor
  - [ ] Dropdown listing all possible worlds
  - [ ] Setting chosen_world_id marks branch as resolved
- [ ] Wire up to controller (needs `update_branch()` to support chosen_world_id)

## DAG View: Completion Status Indicators

- [ ] Task nodes show visual indicator for status:
  - [ ] Not started: default styling
  - [ ] In progress: distinct color/border (e.g., yellow border)
  - [ ] Completed: distinct color/icon (e.g., green with checkmark)
- [ ] Branch nodes show resolved state:
  - [ ] Unresolved: default styling
  - [ ] Resolved: show which world was chosen, gray out others

## List View: Completion Status Display

- [ ] Add status indicator to list items:
  - [ ] Task items show [Not Started], [In Progress], or [Completed]
  - [ ] Branch items show [Unresolved] or [Resolved: <world>]
- [ ] Consider adding filter/sort by status

## Controller Updates

- [ ] Verify `update_task()` handles completion fields correctly
- [ ] Add `update_branch()` support for `chosen_world_id` if not present
- [ ] Ensure undo/redo works for completion state changes

## Testing

- [ ] Unit tests for task completion state transitions
- [ ] Unit tests for branch resolution
- [ ] GUI tests for task editor completion section
- [ ] GUI tests for branch editor resolution section
- [ ] GUI tests for DAG view status indicators
- [ ] GUI tests for list view status display
