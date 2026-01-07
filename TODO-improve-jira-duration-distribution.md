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
3. Unit tests for `find_empirical_bin_for_estimate()` (including tie-breaking to higher bin)
4. Integration tests for `sample_task_duration()` with `JiraDurationDistribution`
5. End-to-end simulation test with Jira-imported project
6. Edge case tests: no history, no estimate, single sample bin
7. Filtered sampling tests for in-progress tasks:
   - Filter removes values <= hours_logged
   - Fallback to all-history bin when filtered bin is empty
   - "Unknown issue" path: hours_logged + sampled when all history exhausted
8. CLI export tests:
   - CSV generation with all columns
   - Correct bin_centers calculation
   - Empty history handling
9. Extended history entry tests for new fields

### Phase 7: Extend History Model for EDA

**File**: `src/fluxx/jira/models.py`

Current `JiraDurationHistoryEntry` has:
- `server_url`, `issue_key`, `original_estimate_seconds`, `worker_jira_id`, `issue_type`, `total_logged_time_seconds`

Add new fields for CSV export:
```python
class JiraDurationHistoryEntry(BaseModel):
    # ... existing fields ...

    # New fields for EDA
    remaining_estimate_seconds: int | None = Field(
        default=None, description="Remaining estimate in seconds at resolution"
    )
    story_points: float | None = Field(
        default=None, description="Story points assigned to the issue"
    )
    created_datetime: datetime | None = Field(
        default=None, description="When the issue was created"
    )
    resolved_datetime: datetime | None = Field(
        default=None, description="When the issue was resolved"
    )
```

**File**: `src/fluxx/jira/extraction.py`

Update history extraction to populate the new fields from Jira issue data.

### Phase 8: CLI Export for Exploratory Data Analysis

**File**: `src/fluxx/__main__.py` (and new `src/fluxx/jira/export.py`)

Add command-line parameter `--write-historical-data-csv <output-filename.csv>` that exports history data for EDA.

1. Add CLI argument parsing:
   ```
   fluxx project.fluxx --write-historical-data-csv output.csv
   ```

2. CSV columns:
   - `issue_key`: Jira issue key (e.g., "PROJ-123")
   - `original_estimate_seconds`: Original estimate from Jira (or empty)
   - `actual_seconds`: Total logged time (or empty)
   - `remaining_seconds`: Remaining estimate (or empty)
   - `story_points`: Story points (or empty)
   - `issue_created_datetime`: When the issue was created
   - `issue_resolved_datetime`: When the issue was resolved
   - `bin_centers`: Pipe-separated list of bin centers that contain this (estimate, actual) pair

3. Implementation in `src/fluxx/jira/export.py`:
   ```python
   def write_historical_data_csv(
       project: Project,
       output_path: Path,
       min_samples_per_bin: int = 30,
   ) -> None:
       """Export historical duration data to CSV for exploratory analysis."""
       # Extract history entries
       # Build bins to determine which bins each entry belongs to
       # Write CSV with all columns
   ```

4. The `bin_centers` column helps analyze which historical data points inform each bin

### Phase 9: Migration

1. Existing `.fluxx` files with `JiraDurationDistribution` should work unchanged (model already stores the parameters)
2. Migration needed for `JiraDurationHistoryEntry` to add new fields (Pydantic handles missing fields with defaults)
3. Users may need to re-sync history to populate new fields (created_datetime, resolved_datetime, etc.)

---

## Design Decisions (Clarified)

1. **Fallback behavior**: When a task has `JiraDurationDistribution` but no `original_estimate_seconds`:
   - **Decision**: Use all history as fallback - sample from all historical (estimate, actual) pairs

2. **Bin selection tie-breaking**: When equidistant from two bins:
   - **Decision**: Pick the higher estimate bin (conservative approach)

3. **History scope**:
   - **Decision**: All projects combined - more data, better statistical power

4. **Old code deprecation**:
   - **Decision**: Remove old fitted ShiftedLognormal approach, keep only empirical sampling

5. **Units storage**:
   - **Decision**: Keep storing in seconds (no breaking change), convert to hours for display and bin matching

6. **Story points and remaining estimate**:
   - For MVP, ignored when choosing a bin (only use `original_estimate_seconds`)
   - Future iterations may incorporate these

---

## Detailed Implementation

### Phase 2: Data Model Changes (Details)

**New data structures in `src/fluxx/jira/distributions.py`**:

```python
@dataclass
class EmpiricalEstimateBin:
    """A bin containing historical (estimate, actual) pairs for empirical sampling.

    Unlike EstimateBin which stores a fitted distribution, this stores the raw
    pairs and samples directly from them.
    """
    center_estimate: float  # in hours
    lower_bound: float      # in hours (exclusive)
    upper_bound: float      # in hours (inclusive)
    samples: list[tuple[float, float]]  # (estimate_hours, actual_hours) pairs

    def sample(self, rng: np.random.Generator) -> float:
        """Randomly select an actual duration from this bin's samples."""
        index = rng.integers(0, len(self.samples))
        return self.samples[index][1]  # Return the actual duration
```

**Bin creation algorithm**:
- Convert all `JiraDurationHistoryEntry` to (estimate_hours, actual_hours) pairs
- Filter out entries without estimates for binning (but keep for fallback)
- Group by estimate with minimum 30 samples per bin
- Store all (estimate, actual) pairs in each bin (not just actuals)

### Phase 3: Simulation Integration (Details)

**Sampling flow**:
1. At simulation start, call `prepare_jira_sampling_context(project)`:
   - Extract history entries from `project.jira_config.sync_metadata.history_entries`
   - Convert seconds to hours for all estimates and actuals
   - Create bins using `create_empirical_bins()`
   - Store in `JiraSamplingContext`

2. In `sample_task_duration()` for `JiraDurationDistribution`:
   ```python
   if isinstance(dist, JiraDurationDistribution):
       if context is None:
           raise ValueError("JiraDurationDistribution requires sampling context")

       if dist.original_estimate_seconds is not None:
           estimate_hours = dist.original_estimate_seconds / 3600
           bin = find_empirical_bin_for_estimate(estimate_hours, context.bins)
       else:
           # No estimate: use fallback bin containing all samples
           bin = context.fallback_bin

       return bin.sample(rng)
   ```

3. **Tie-breaking**: When equidistant from two bins, pick the one with higher center_estimate

### Phase 4: Edge Cases (Details)

1. **No history data at all**:
   - **Decision**: Use exponential distribution with mean = original estimate
   - Exponential is the maximum entropy distribution when only the mean is known
   - This should be rare in practice (why use JiraDurationDistribution without data?)
   - Implementation: `rng.exponential(scale=estimate_hours)`

2. **Task has no estimate AND no history**:
   - Use exponential with a sensible default mean (e.g., 8 hours = 1 workday)
   - Log a warning

3. **Task has no estimate but history exists**:
   - Use fallback bin containing ALL historical (estimate, actual) pairs
   - Sample uniformly from all actuals regardless of estimate

4. **In-progress tasks with JiraDurationDistribution** (filtered sampling, not rejection):
   - Filter the bin to only include samples where actual > hours_logged
   - If filtered bin is non-empty: sample uniformly from remaining values
   - If filtered bin is empty: filter the fallback bin the same way
   - If fallback bin also empty (hours_logged > all historical actuals):
     - Treat remaining work as an "unknown issue"
     - Sample from unfiltered fallback distribution
     - Return: hours_logged + sampled_value
   - This avoids rejection sampling entirely and handles edge cases gracefully
