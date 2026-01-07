# Plan: Generate Missing Features List

## Objective

Systematically review `project_fluxx_specification.md` section by section, comparing against the actual implementation to identify:
1. Features mentioned but not implemented
2. Features partially implemented
3. Backend features not exposed in the UI

Results will be appended to `missing_features.md` with enough context for future implementation.

---

## Investigation Approach

For each section:
1. Read the specification requirements
2. Search codebase for relevant implementations (grep for key terms, check relevant files)
3. For GUI features: verify both backend and frontend exist
4. Document findings in `missing_features.md`

---

## Section Checklist

### Section 2: Core Concepts

#### 2.1 Nodes
- [ ] **Task worker constraints**: Check `excluded_worker_tasks` implementation
  - Files: `src/fluxx/data/models.py`, `src/fluxx/simulation/scheduler.py`
  - GUI: Task editor should show excluded assignees section

#### 2.2 Duration Distributions
- [x] ShiftedLognormal - Known implemented
- [x] Triangular - Known implemented
- [x] JiraDurationDistribution - Known implemented (recent work)

#### 2.3 Possible Worlds
- [ ] Verify possible world weight/probability display in UI
  - GUI: Branch editor should show computed probability column

#### 2.4 Workers
- [ ] Worker ID field (optional, to distinguish same-named workers)
  - Files: `src/fluxx/data/models.py`
  - GUI: Worker editor should have ID column

---

### Section 3: Data Model

#### 3.1.1 Task Completion Schema
- [ ] `DoneCompletion.assignee` can be None (for unrecorded assignees)
- [ ] Verify all completion state transitions work in UI
  - "Start Task", "Complete Task", "Reopen Task", "Become not started"

#### 3.3.5 Visualization Implications
- [ ] Dependency edges connect to appropriate side of node boxes
  - Start dependencies → left side
  - End dependencies → right side
  - Files: `src/fluxx/gui/widgets/dag_view.py` or similar

#### 3.6 Simulation Schema
- [ ] Checkpoint data storage and resumption
  - `last_checkpoint`, `rng_state` fields
  - Files: `src/fluxx/data/models.py`, `src/fluxx/simulation/engine.py`

---

### Section 4: Project Persistence

#### 4.2 Saving
- [ ] Auto-save every 5 minutes (configurable)
  - Files: Check for autosave timer in GUI code
- [ ] Auto-save to `.fluxx_autosave/` directory
- [ ] Atomic save (write to .tmp then rename)

#### 4.3 Loading
- [ ] Recent Files menu (5 most recent projects)
- [ ] Recovery prompt for auto-save files on startup

#### 4.4 Version Compatibility
- [ ] Forward compatibility warning for newer files
- [ ] Backup before migration: `<filename>.backup_v<old_version>`

#### 4.5 File Menu Structure
- [ ] Export submenu with "Export to CSV" and "Export Gantt Chart"

#### 4.6 New Project
- [ ] Create default worker "Worker 1" with 8 hours/day

---

### Section 5: User Interface

#### 5.2.1 Control Bar
- [ ] History Widget with dropdown for history tree navigation
- [ ] View Mode Toggle (DAG vs list display)

#### 5.2.2 DAG Display Mode
- [ ] Collapsible nodes (hide subtasks)
- [ ] Assignee exclusions: purple line with 🚫 symbol

#### 5.2.3 List Display Mode
- [ ] Fuzzy search using RapidFuzz
  - Files: Check if rapidfuzz is in dependencies

#### 5.3.2 Task Node Editor
- [ ] Duration distribution visualization/preview
- [ ] "Convert to Parent" button for leaf tasks
- [ ] "Add Sibling" button for child tasks
- [ ] Completion tracking UI:
  - "Start Task" section with assignee dropdown, datetime picker
  - "Complete Task" section
  - "Reopen Task" button
  - "Become not started" button

#### 5.3.3 Branch Node Editor
- [ ] Probability column (computed from weights)
- [ ] "Resolve Branch" dropdown

#### 5.3.4 Edit Modes
- [ ] Select-task-node mode for excluded assignees
- [ ] Visual indicator "Select a task to exclude..."

#### 5.3.5 Navigation and Change Management
- [ ] Modal on navigation with unapplied changes
- [ ] Error message explaining validation issues

#### 5.4 Worker List Editor
- [ ] Worker ID column (optional)
- [ ] Description column

#### 5.5 Simulation Management
- [ ] Simulation list with status, failure rate
- [ ] "Resume" button for interrupted simulations
- [ ] "Add More Samples" button
- [ ] "Generate Probabilistic Timeline" button
- [ ] Checkpoint time display during simulation

#### 5.6 History Tree Navigation
- [ ] Full history tree visualization (not just linear)
- [ ] Navigate to branches created by undo+different action

---

### Section 6: Dependencies and Constraints

#### 6.1 Task-Task Dependencies
- [ ] Equality constraint type (=) in addition to (>=)
  - Files: `src/fluxx/data/models.py`
  - GUI: Constraint type dropdown

#### 6.4 Worker Constraints
- [ ] Excluded Assignees validation: require N.start >= M.start dependency
  - Files: `src/fluxx/data/validation.py`

---

### Section 7: Simulation Engine

#### 7.2 Simulation Mechanics
- [ ] Holidays, vacations, sick days (mentioned as future)
  - Files: `src/fluxx/simulation/calendar.py`

#### 7.5 Checkpointing and Resuming
- [ ] Checkpoint every 100 samples (configurable)
- [ ] Resume from checkpoint on app startup
- [ ] RNG state serialization per parallel process

---

### Section 8: Visualizations

#### 8.1 Gantt Charts
- [ ] Horizontal dividers separating world sequence groups
- [ ] Task variants sorted by possible world sequence

#### 8.2 Probabilistic Timeline
- [ ] Full implementation as described
  - Min/max start/end times
  - (1-P)th and Pth percentile markers
  - Occurrence fraction per task
  - Files: Check if this visualization exists

---

### Section 9: History System

#### 9.2 Branching History
- [ ] Tree structure navigation (not just linear undo/redo)
- [ ] Navigate to either branch after undo+different action

---

### Section 11: Jira Integration

#### 11.2 Configuration
- [ ] Rate limit setting in import dialog (requests/second)
- [ ] Token path: `~/.local/share/secrets/...` (vs `~/.fluxx/jira_tokens/`)

#### 11.4.1 Import Dialog
- [ ] Rate limit setting control
- [ ] Progress bar with cancel button
- [ ] Error display with retry option

#### 11.4.3 Hierarchy Mapping
- [ ] Sub-epic detection and warning

#### 11.4.4 Dependency Mapping
- [ ] "schedule after"/"schedule before" link type support
- [ ] Special case: remove dependency when both tasks started

#### 11.8 Linking Existing Tasks to Jira
- [ ] Jira Issue field in Task Editor
- [ ] Field overwrite warning dialog

#### 11.9 "Become Child Of" Feature
- [ ] Button in Task Editor
- [ ] Select-task-node mode
- [ ] Conflict detection and dialog

---

## Execution Order

1. **High Priority** - Core simulation and data model gaps:
   - Section 3.6 (Checkpointing)
   - Section 7.5 (Resume simulations)
   - Section 6.4 (Worker constraint validation)

2. **Medium Priority** - UI completeness:
   - Section 5.2-5.5 (All editor features)
   - Section 4.2-4.3 (Auto-save, recovery)

3. **Lower Priority** - Polish and advanced features:
   - Section 8 (Visualizations)
   - Section 9 (History tree UI)
   - Section 11 (Jira integration gaps)

---

## Output Format

For each missing/partial feature, add to `missing_features.md`:

```markdown
## N. Feature Name

**Source**: `project_fluxx_specification.md`, Section X.Y

**Status**: Not implemented / Partial / Backend only

### Description
[What the spec says]

### Current State
[What exists now, if anything]

### Implementation Notes
[Key files, algorithms, dependencies]

### Acceptance Criteria
[How to know when done]
```

---

## Notes

- Some features in Section 12 ("Future Improvements") are explicitly deferred - skip these
- Focus on features described as current requirements in Sections 1-11
- When uncertain if something is implemented, search for key terms in codebase before documenting
