# Plan: Improve Jira Duration Distribution Sampling

## Overview

Replace the fitted ShiftedLognormal bin-based approach with an empirical multiset sampling approach for `JiraDurationDistribution`. Tasks imported from Jira will store their estimate parameters, and at simulation time, we sample actual durations by finding the closest bin based on estimate and randomly choosing from historical (estimate, actual) pairs in that bin.

## Current State

- `JiraDurationDistribution` exists in `src/fluxx/data/models.py` with fields:
  - `original_estimate_seconds: int | None`
  - `story_points: float | None`
  - `remaining_estimate_seconds: int | None`
- Jira imports create tasks with `JiraDurationDistribution`
- `sample_task_duration()` in `engine.py` does NOT handle `JiraDurationDistribution` (lines 66-71 only handle Triangular and ShiftedLognormal)
- Current `EstimateBin` stores a fitted `ShiftedLognormal` distribution, not raw samples
- History is stored in `JiraSyncMetadata.history_entries` as `JiraDurationHistoryEntry` list

## Goals

1. Store empirical (estimate, actual) pairs in bins instead of fitted distributions
2. Sample by randomly selecting a pair from the closest bin
3. Pre-calculate bins at simulation start from synchronized history
4. Update specification section 2.2 to document `JiraDurationDistribution`

---

## Implementation Steps

### Phase 1: Update Specification

**File**: `project_fluxx_specification.md`

1. Amend section 2.2 to include `JiraDurationDistribution`:
   ```
   3. **JiraDurationDistribution**: For Jira-imported tasks. Stores:
      - original_estimate_seconds (displayed as hours)
      - story_points
      - remaining_estimate_seconds (displayed as hours)

   Sampling: Uses an empirical bin-based approach. At simulation start,
   historical (estimate, actual) pairs are grouped into bins. To sample,
   find the bin whose center estimate is closest to the task's
   original_estimate, then randomly select an actual duration from that bin's
   multiset of historical values.
   ```

2. Add detailed specification for binned empirical distribution model (likely new subsection 2.2.1 or similar)

### Phase 2: Data Model Changes

**File**: `src/fluxx/jira/distributions.py`

1. Create new `EmpiricalEstimateBin` dataclass:
   ```python
   @dataclass
   class EmpiricalEstimateBin:
       center_estimate: float  # in hours
       lower_bound: float
       upper_bound: float
       samples: list[tuple[float, float]]  # (estimate_hours, actual_hours) pairs
   ```

2. Add `sample()` method to `EmpiricalEstimateBin`:
   - Randomly choose an index from `samples`
   - Return the actual duration from that pair

3. Create `create_empirical_bins()` function:
   - Input: list of `JiraDurationHistoryEntry`
   - Output: list of `EmpiricalEstimateBin`
   - Group entries by estimate, store (estimate, actual) pairs
   - Minimum samples per bin (configurable, default 30)

4. Create `find_empirical_bin_for_estimate()` function:
   - Find bin whose center_estimate is closest to the query estimate

### Phase 3: Simulation Integration

**File**: `src/fluxx/simulation/engine.py`

1. Add `JiraSamplingContext` dataclass to hold pre-computed bins:
   ```python
   @dataclass
   class JiraSamplingContext:
       bins: list[EmpiricalEstimateBin]
       fallback_distribution: ShiftedLognormal | None  # For tasks without estimates
   ```

2. Add `prepare_jira_sampling_context()` function:
   - Called at simulation start
   - Takes project history entries
   - Returns `JiraSamplingContext` with pre-computed bins

3. Modify `sample_task_duration()` to handle `JiraDurationDistribution`:
   - Add `sampling_context: JiraSamplingContext | None` parameter
   - If task has `JiraDurationDistribution`:
     - Convert `original_estimate_seconds` to hours
     - Find closest bin using `find_empirical_bin_for_estimate()`
     - Sample from that bin's multiset
   - Handle edge case: no estimate available (use fallback distribution)

4. Update `run_single_sample()` to:
   - Call `prepare_jira_sampling_context()` at start
   - Pass context to `sample_task_duration()`

### Phase 4: Handle Edge Cases

1. **No history data**: Fall back to a default distribution or raise clear error
2. **Task has no estimate**: Use fallback distribution from all history
3. **Empty bin match**: Should not happen with proper binning, but handle gracefully
4. **In-progress tasks**: Extend `sample_in_progress_task_remaining_duration()` to handle `JiraDurationDistribution` with rejection sampling

### Phase 5: Update GUI Display

**File**: `src/fluxx/gui/widgets/task_editor.py` (and related)

1. Display `JiraDurationDistribution` fields in hours (convert from seconds):
   - `original_estimate_seconds / 3600` -> "Original Estimate: X hours"
   - `remaining_estimate_seconds / 3600` -> "Remaining Estimate: X hours"
   - `story_points` as-is

### Phase 6: Tests

1. Unit tests for `EmpiricalEstimateBin.sample()`
2. Unit tests for `create_empirical_bins()`
3. Unit tests for `find_empirical_bin_for_estimate()`
4. Integration tests for `sample_task_duration()` with `JiraDurationDistribution`
5. End-to-end simulation test with Jira-imported project
6. Edge case tests: no history, no estimate, single sample bin

### Phase 7: Migration

1. Existing `.fluxx` files with `JiraDurationDistribution` should work unchanged (model already stores the parameters)
2. No migration needed for the distribution model itself
3. Consider if any cached/fitted distributions need invalidation

---

## Open Questions for User

1. **Fallback behavior**: What should happen when a task has a `JiraDurationDistribution` but:
   - No `original_estimate_seconds`? (Use all history as fallback bin?)
   - No history data at all? (Error? Use a hardcoded default?)

2. **Minimum bin size**: Current code uses 30 samples per bin. Should this be configurable or is 30 acceptable?

3. **Bin selection tie-breaking**: If equidistant from two bins, should we:
   - Pick the lower estimate bin?
   - Pick the higher estimate bin?
   - Pick randomly between them?

4. **History scope**: Should binning use:
   - Only history from the same Jira project?
   - All history across all synchronized projects?

5. **Units consistency**: The model stores `original_estimate_seconds` but you mentioned "displayed in hours". Should we:
   - Keep storing in seconds (current) and convert for display?
   - Change the model to store hours (breaking change)?

6. **Story points and remaining estimate**: For this MVP, we're ignoring these fields when choosing a bin. Is this correct? Should they be considered in future iterations?

7. **Deprecation**: Should we deprecate/remove the old `fit_bin_distribution()` and `EstimateBin.distribution` code paths, or keep them as alternatives?
