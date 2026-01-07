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
