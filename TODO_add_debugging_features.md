# TODO: Add Debugging Features

## Summary

Add comprehensive debugging capabilities to Project Fluxx to aid in diagnosing simulation issues and Jira integration problems. This includes:

1. `--run-simulation N` CLI option to run simulations headlessly
2. Debug-level logging throughout simulation code
3. `--log-level DEBUG` CLI option to control log verbosity
4. `--write-simulation-results-json filename_base` to export simulation results
5. Debug-level logging throughout Jira integration code

---

## Objectives

- Enable CLI-based simulation debugging without GUI
- Provide visibility into simulation internals via structured logging
- Support automated testing and CI/CD pipelines
- Aid diagnosis of Jira import/sync issues
- Maintain 100% test coverage and type safety

---

## Specification Update Plan

The debugging features should be added to `project_fluxx_specification.md` in two new subsections under Section 10 (Implementation Considerations):

### Section 10.4 Command-Line Interface

Document the new CLI options:
- `--run-simulation N` - Run simulation immediately and exit
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` - Set logging verbosity
- `--write-simulation-results-json filename_base` - Export simulation results to JSON
- Document interaction between options (e.g., `--run-simulation` combined with `--write-simulation-results-json`)

### Section 10.5 Logging and Diagnostics

Document:
- Logging infrastructure using Python's `logging` module
- Key events logged at each level (DEBUG, INFO, WARNING, ERROR)
- Log format and output destination (stderr)
- Covered areas: simulation engine, scheduler, state management, Jira client, import/sync

---

## Investigation Protocol

After each phase, perform the following investigation:

1. Review the implementation against the specification
2. Test the feature manually with real data (when applicable)
3. Check for edge cases not covered by tests
4. Document any omissions or deferred features in `missing_features.md`

### Format for missing_features.md

When adding entries, use this format (from `TODO_generate_missing_features_list.md`):

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

## Phase 1: Logging Infrastructure and `--log-level` Option

### 1.1 Create logging configuration module

Add a module to set up logging with consistent formatting.

- [ ] Create `src/fluxx/logging_config.py` with:
  - `configure_logging(level: str) -> None` function
  - Format: `%(asctime)s %(levelname)s [%(name)s] %(message)s`
  - Output to stderr (not stdout, to avoid mixing with data output)
  - Default level: INFO

**File**: `src/fluxx/logging_config.py` (new)

### 1.2 Add `--log-level` CLI argument

Add the argument to the CLI parser.

- [ ] Add `--log-level` argument to `src/fluxx/__main__.py`
  - Choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
  - Default: `INFO`
  - Case-insensitive
- [ ] Call `configure_logging()` early in `main()`

**File**: `src/fluxx/__main__.py`

### 1.3 Add tests for logging configuration

- [ ] Test `configure_logging()` sets correct level
- [ ] Test CLI argument parsing for `--log-level`
- [ ] Test case-insensitivity of log level argument
- [ ] Test default log level is INFO

**File**: `tests/test_logging_config.py` (new), `tests/test_main.py`

### 1.4 Investigation checkpoint

- [ ] Verify logging works correctly with various levels
- [ ] Check that log output goes to stderr
- [ ] Document any limitations in `missing_features.md` if needed

---

## Phase 2: Debug Logging in Simulation Code

### 2.1 Add logging to simulation engine

Add logger and debug statements to the main simulation loop.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at INFO level:
  - Simulation start with parameters (num_samples, start_date, num_processes)
  - Simulation complete with timing
  - Overall failure rate
- [ ] Log at DEBUG level:
  - Each sample start/complete
  - Sample failure with failed task IDs
  - Checkpoint creation

**File**: `src/fluxx/simulation/engine.py`

### 2.2 Add logging to scheduler

Add logging for task selection and worker assignment decisions.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at DEBUG level:
  - Eligible tasks at each scheduling step
  - Available workers
  - Task-worker assignment decisions
  - Why a task was skipped (dependencies, worker constraints)
  - Deadlock detection

**File**: `src/fluxx/simulation/scheduler.py`

### 2.3 Add logging to simulation state

Add logging for state transitions.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at DEBUG level:
  - Task state changes (not_started → started → done)
  - Branch resolution (which world was chosen)
  - Worker state changes (idle → busy → idle)
  - Time advancement

**File**: `src/fluxx/simulation/state.py`

### 2.4 Add logging to duration sampling

Add logging for duration distribution sampling.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at DEBUG level:
  - Distribution type being sampled
  - Parameters used
  - Sampled value
  - Rejection sampling iterations (for in-progress tasks)
  - Fallback to exponential when needed

**File**: `src/fluxx/simulation/distributions.py`

### 2.5 Add logging to calendar

Add logging for calendar calculations.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at DEBUG level:
  - Work hour calculations
  - Weekend skipping
  - Date/time conversions

**File**: `src/fluxx/simulation/calendar.py`

### 2.6 Add tests for simulation logging

- [ ] Test that INFO messages appear for simulation start/end
- [ ] Test that DEBUG messages appear for sample progress
- [ ] Test log output contains expected information (task IDs, sample IDs)
- [ ] Use pytest's `caplog` fixture to capture and verify logs

**File**: `tests/simulation/test_engine_logging.py` (new)

### 2.7 Investigation checkpoint

- [ ] Run simulation with `--log-level DEBUG` on test project
- [ ] Verify log output is informative and not too verbose
- [ ] Check that simulation performance is not significantly impacted
- [ ] Document any missing log points in `missing_features.md` if needed

---

## Phase 3: `--run-simulation N` CLI Option

### 3.1 Add `--run-simulation` CLI argument

Add the argument to run simulations without GUI.

- [ ] Add `--run-simulation N` argument to `src/fluxx/__main__.py`
  - N is the number of samples to run
  - Requires a project file to be specified
  - Mutually exclusive with `--write-historical-data-csv`
- [ ] Add `--simulation-start-date` optional argument
  - ISO 8601 format datetime
  - Default: next workday at 9:00 AM

**File**: `src/fluxx/__main__.py`

### 3.2 Implement headless simulation runner

Create a function to run simulations without GUI.

- [ ] Add `run_simulation_headless()` function:
  - Load project from file
  - Create SimulationEngine with specified parameters
  - Extract workers from project
  - Run simulation
  - Print summary to stdout (samples run, failure rate, elapsed time)
  - Return exit code (0 success, 1 if all samples failed)
- [ ] Call this function when `--run-simulation` is specified
- [ ] Exit after simulation completes (don't launch GUI)

**File**: `src/fluxx/__main__.py`

### 3.3 Add tests for headless simulation

- [ ] Test CLI argument parsing
- [ ] Test successful simulation run with exit code 0
- [ ] Test simulation with some failures
- [ ] Test error handling (file not found, invalid project)
- [ ] Test mutually exclusive arguments
- [ ] Test `--simulation-start-date` parsing

**File**: `tests/test_main.py`

### 3.4 Investigation checkpoint

- [ ] Test with the problematic `FHIR-3323-fy26-incremental-sync.fluxx` file
- [ ] Verify output is useful for debugging
- [ ] Check that logging works correctly in headless mode
- [ ] Document any limitations in `missing_features.md` if needed

---

## Phase 4: `--write-simulation-results-json` CLI Option

### 4.1 Add `--write-simulation-results-json` CLI argument

Add the argument for JSON output.

- [ ] Add `--write-simulation-results-json filename_base` argument
  - Only valid with `--run-simulation`
  - Writes results after simulation completes

**File**: `src/fluxx/__main__.py`

### 4.2 Implement simulation results JSON export

Create a function to export simulation results.

- [ ] Add `write_simulation_results_json()` function:
  - Accept `filename_base` and `Simulation` object
  - Find available filename: `{base}.1.fluxx_simulation.json`, increment if exists
  - Serialize simulation using Pydantic's `model_dump(mode="json")`
  - Include metadata:
    - `export_timestamp`: When the export was created
    - `fluxx_version`: Application version
    - `project_file`: Source project file path
  - Write with `indent=2` for readability
  - Print filename to stdout after writing
- [ ] Call after successful simulation in headless mode

**File**: `src/fluxx/__main__.py` (or new `src/fluxx/simulation/export.py`)

### 4.3 Add tests for JSON export

- [ ] Test filename increment logic (1, 2, 3, ...)
- [ ] Test JSON output is valid and parseable
- [ ] Test all simulation fields are included
- [ ] Test metadata is correct
- [ ] Test file writing errors are handled

**File**: `tests/test_main.py` or `tests/simulation/test_export.py`

### 4.4 Investigation checkpoint

- [ ] Verify JSON output matches simulation data model
- [ ] Check that large simulations serialize correctly
- [ ] Test that exported files can be loaded with standard JSON tools
- [ ] Document any serialization limitations in `missing_features.md` if needed

---

## Phase 5: Debug Logging in Jira Integration Code

### 5.1 Add logging to Jira client

Add logging for HTTP requests and rate limiting.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at INFO level:
  - Request to Jira (method, URL without credentials)
  - Response status code
- [ ] Log at DEBUG level:
  - Request parameters (JQL, fields)
  - Response size
  - Rate limit delay
  - Retry attempts

**File**: `src/fluxx/jira/client.py`

### 5.2 Add logging to Jira importer

Add logging for import process.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at INFO level:
  - Import start with epic key
  - Number of issues fetched
  - Number of workers imported
  - Import complete with timing
- [ ] Log at DEBUG level:
  - Each issue being processed
  - Hierarchy decisions
  - Dependency mapping
  - Completion state mapping
  - Deduplication decisions

**File**: `src/fluxx/jira/importer.py`

### 5.3 Add logging to Jira extraction

Add logging for data extraction.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at DEBUG level:
  - Field extraction for each issue
  - Missing or invalid fields
  - Worklog processing
  - Worker matching

**File**: `src/fluxx/jira/extraction.py`

### 5.4 Add logging to Jira distributions

Add logging for distribution fitting.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at INFO level:
  - Number of history entries used
  - Number of bins created
- [ ] Log at DEBUG level:
  - Bin boundaries
  - Samples per bin
  - Distribution parameters fitted
  - Fallback distribution used

**File**: `src/fluxx/jira/distributions.py`

### 5.5 Add logging to Jira auth

Add logging for authentication.

- [ ] Add `logger = logging.getLogger(__name__)` at module level
- [ ] Log at DEBUG level:
  - Token path being checked
  - Token found/not found (never log token content!)
- [ ] Log at WARNING level:
  - Token file permissions issues
  - Authentication failures

**File**: `src/fluxx/jira/auth.py`

### 5.6 Add tests for Jira logging

- [ ] Test that INFO messages appear for import start/end
- [ ] Test that DEBUG messages appear for detailed operations
- [ ] Test that credentials are never logged
- [ ] Use pytest's `caplog` fixture

**File**: `tests/jira/test_logging.py` (new)

### 5.7 Investigation checkpoint

- [ ] Test Jira import with `--log-level DEBUG` (if applicable via GUI or future CLI option)
- [ ] Verify log output helps diagnose import issues
- [ ] Check that sensitive data (tokens) is never logged
- [ ] Document any missing log points in `missing_features.md` if needed

---

## Phase 6: Update Specification

### 6.1 Add Section 10.4 Command-Line Interface

- [ ] Document all CLI options including existing ones
- [ ] Document option interactions and mutual exclusivity
- [ ] Provide usage examples
- [ ] Document exit codes

### 6.2 Add Section 10.5 Logging and Diagnostics

- [ ] Document logging infrastructure
- [ ] List log levels and what they include
- [ ] Document covered subsystems
- [ ] Provide debugging tips

### 6.3 Review and cross-reference

- [ ] Ensure new sections are referenced from relevant existing sections
- [ ] Update table of contents if present
- [ ] Check for consistency with existing documentation style

**File**: `project_fluxx_specification.md`

### 6.4 Investigation checkpoint

- [ ] Compare specification to implementation
- [ ] Verify all documented features work as described
- [ ] Document any gaps in `missing_features.md`

---

## Phase 7: Final Integration and Documentation

### 7.1 Integration testing

- [ ] Test all new CLI options together
- [ ] Test with real problematic project files
- [ ] Verify logging works correctly in all modes (GUI and headless)
- [ ] Performance testing (ensure logging doesn't significantly slow simulation)

### 7.2 Update CLAUDE.md

- [ ] Add debugging section with common workflows
- [ ] Document new CLI options
- [ ] Provide example commands for debugging

**File**: `CLAUDE.md`

### 7.3 Final investigation

- [ ] Complete review of all phases
- [ ] Finalize `missing_features.md` entries if any
- [ ] Verify test coverage meets requirements (100% non-GUI, 90%+ GUI)
- [ ] Run `make all_checks` to ensure all quality gates pass

---

## Implementation Notes

### Logging Best Practices

1. **Log levels**:
   - ERROR: Unrecoverable errors
   - WARNING: Recoverable issues, unexpected but handled
   - INFO: Major milestones, user-relevant progress
   - DEBUG: Detailed internal state, developer-focused

2. **Avoid logging**:
   - Credentials, tokens, passwords (security)
   - Large data structures in their entirety (performance)
   - Inside tight loops at DEBUG without gating

3. **Log message format**:
   - Use structured data: `logger.debug("Task assigned", extra={"task_id": task_id, "worker_id": worker_id})`
   - Or formatted strings: `logger.debug(f"Task {task_id} assigned to worker {worker_id}")`

### File Naming for JSON Export

The increment logic for `--write-simulation-results-json`:
```python
def find_available_filename(base: str) -> Path:
    n = 1
    while True:
        path = Path(f"{base}.{n}.fluxx_simulation.json")
        if not path.exists():
            return path
        n += 1
```

### Exit Codes

- 0: Success
- 1: Simulation failure (all samples failed or other error)
- 2: Invalid arguments
- 3: File not found or invalid project

---

## Testing Checklist

- [ ] Logging configuration unit tests pass
- [ ] CLI argument parsing tests pass
- [ ] Headless simulation tests pass
- [ ] JSON export tests pass
- [ ] Simulation logging tests pass
- [ ] Jira logging tests pass
- [ ] Integration tests pass
- [ ] 100% non-GUI test coverage maintained
- [ ] 90%+ GUI test coverage maintained
- [ ] `make all_checks` passes
- [ ] Manual testing with problematic project files

---

## Related Files

- `src/fluxx/__main__.py` - CLI entry point
- `src/fluxx/logging_config.py` - Logging configuration (new)
- `src/fluxx/simulation/engine.py` - Simulation engine
- `src/fluxx/simulation/scheduler.py` - Task scheduler
- `src/fluxx/simulation/state.py` - Simulation state
- `src/fluxx/simulation/distributions.py` - Duration distributions
- `src/fluxx/simulation/calendar.py` - Calendar logic
- `src/fluxx/jira/client.py` - Jira HTTP client
- `src/fluxx/jira/importer.py` - Jira import logic
- `src/fluxx/jira/extraction.py` - Data extraction
- `src/fluxx/jira/distributions.py` - Duration fitting
- `src/fluxx/jira/auth.py` - Authentication
- `project_fluxx_specification.md` - Specification
- `CLAUDE.md` - Developer guide
- `missing_features.md` - Feature gap tracking

---

## Estimated Effort by Phase

| Phase | Description | Estimated Effort |
|-------|-------------|------------------|
| 1 | Logging infrastructure and `--log-level` | 1-2 hours |
| 2 | Debug logging in simulation code | 2-3 hours |
| 3 | `--run-simulation N` CLI option | 2-3 hours |
| 4 | `--write-simulation-results-json` | 1-2 hours |
| 5 | Debug logging in Jira integration | 2-3 hours |
| 6 | Update specification | 1 hour |
| 7 | Final integration and documentation | 1-2 hours |

**Total: ~10-16 hours**
