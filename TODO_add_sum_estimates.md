# Plan: Add Summed Child Estimates to History Entries

## Goal

Enable historical data collection for parent tasks by summing the original estimates of their closed child tasks. This provides estimate data for longer-timeline items that have been decomposed into subtasks (and thus no longer have their own original estimate).

## Background

Currently, when a parent task is broken down into child tasks in Jira:
- The parent task's `original_estimate_seconds` is often `None` (no direct estimate)
- Only individual child task estimates are captured in history
- This means we lack historical data for estimating similar parent-level work items

The solution: When a parent task is closed and all its children are closed, create a history entry with `original_estimate_seconds` set to the sum of all child estimates (or use the parent's own estimate if it has one).

## Design Decisions

### Decision 1: What if a child has no original estimate?

**Chosen approach**: Recursive fallback with skip on missing leaf estimates.

If a child has no `original_estimate_seconds`:
1. Check if that child is itself a parent with children
2. If yes, recursively compute a summed estimate for that child first
3. If no (leaf node with no estimate), skip creating a summed entry for the current parent

This allows deep hierarchies to work correctly: a grandparent can get a summed estimate even if the intermediate parent has no direct estimate, as long as all leaf nodes have estimates.

**Fallback consideration**: If we find that too few parents qualify for summed entries (due to missing leaf estimates), we may switch to Option B: skip children without estimates and sum the rest. This would underestimate the *original estimate* (not actual work), meaning we'd over-estimate actual work - which is the safer direction to err for business planning.

### Decision 2: How deep should aggregation go?

**Chosen approach**: Sum all descendants (children, grandchildren, etc.), not just direct children.
- Rationale: A parent's total scope includes all nested work.
- Implementation: Traverse hierarchy recursively.

### Decision 3: Parent's own estimate vs. children's sum

A parent issue may have its own `original_estimate_seconds` set directly in Jira (before it was broken down into children).

**Chosen approach**: Prefer the parent's own estimate when available.

- If parent has `original_estimate_seconds > 0`: Use that value with `estimate_source=FROM_ORIGINAL_ESTIMATE`
  - Rationale: This estimate predates the children and reflects the case of estimating a large task without breaking it down - exactly what we want to model.
- If parent has `original_estimate_seconds` of 0 or `None`: Use the summed children's estimate with `estimate_source=FROM_SUMMING_CHILDREN`

This means each parent issue gets exactly one history entry (no deduplication conflict).

### Decision 4: What worker is assigned to parent entries?

**Chosen approach**: Use worker from parent issue itself (same logic as individual entries - worker who logged most time on that issue). If no work logged on parent, leave as `None`.

## Implementation Steps

**Implementation Order Note**: Steps 1-2 (model + migration) must be completed together and tested before moving to Steps 3-5 (importer changes). This ensures:
1. The new field exists in the model
2. Old files can be loaded (migration adds the field)
3. Then new entry creation logic can use the field

### Step 1: Add `estimate_source` field to `JiraDurationHistoryEntry`

**File**: `src/fluxx/jira/models.py`

Add a new required field to track the source of the estimate:

```python
from enum import Enum

class EstimateSource(str, Enum):
    FROM_ORIGINAL_ESTIMATE = "from original estimate field"
    FROM_SUMMING_CHILDREN = "from summing children"
```

Add to `JiraDurationHistoryEntry`:
```python
estimate_source: EstimateSource = Field(
    description="How the estimate was derived"
)
```

This field is required (not optional) to ensure all history entries are properly categorized for future model selection.

### Step 2: Add data migration (version 1.3 → 1.4)

**File**: `src/fluxx/data/migration.py`

Add migration to set `estimate_source` on all existing history entries:

1. Update `CURRENT_VERSION` to `"1.4"`
2. Add `"1.4"` to `SUPPORTED_VERSIONS`
3. Add `migrate_1_3_to_1_4()` function:

```python
def migrate_1_3_to_1_4(json_data: JsonObject) -> JsonObject:
    """Migrate from version 1.3 to 1.4.

    Changes:
    - Adds estimate_source field to JiraDurationHistoryEntry
      (required field, defaults to "from original estimate field" for existing entries)
    """
    jira_config = json_data.get("jira_config")
    if isinstance(jira_config, dict):
        sync_metadata = jira_config.get("sync_metadata")
        if isinstance(sync_metadata, dict):
            history_entries = sync_metadata.get("history_entries", [])
            if isinstance(history_entries, list):
                for entry in history_entries:
                    if isinstance(entry, dict) and "estimate_source" not in entry:
                        entry["estimate_source"] = "from original estimate field"

    json_data["version"] = "1.4"
    return json_data
```

4. Update `migrate_project_data()` to call this new migration after 1.2→1.3

### Step 3: Update `_create_history_entries()` to set `estimate_source`

**File**: `src/fluxx/jira/importer.py`

Modify the existing history entry creation to set `estimate_source=EstimateSource.FROM_ORIGINAL_ESTIMATE` for all entries created from individual issues.

### Step 4: Implement parent task history entry creation

**File**: `src/fluxx/jira/importer.py`

Add a new function `_create_parent_history_entries()`:

```python
def _create_parent_history_entries(
    issues: list[JiraIssueResponse],
    hierarchy: dict[str, HierarchyEntry],
    workers: dict[str, Worker],
    server_url: str,
    server_timezone: str,
) -> list[JiraDurationHistoryEntry]:
```

Logic:
1. Build a mapping of parent_key → list of child issues from the hierarchy
2. For each issue that is a parent (appears as a parent_key in hierarchy):
   - Check if parent is closed (has resolution/done status)
   - Check if ALL children (recursively) are closed
3. Determine the estimate to use (per Decision 3 above):
   - If parent has `original_estimate_seconds > 0`: use it with `estimate_source=FROM_ORIGINAL_ESTIMATE`
   - Else: recursively compute sum of descendants' estimates (per Decision 1 above)
     - If any leaf descendant lacks an estimate, skip this parent entirely
     - Otherwise use the sum with `estimate_source=FROM_SUMMING_CHILDREN`
4. Create history entry with:
   - `original_estimate_seconds` = determined estimate
   - `total_logged_time_seconds` = sum of all descendants' logged time (if all have it; else `None`)
   - `estimate_source` = as determined above
   - Other fields (worker, issue_type, dates) come from the parent issue itself

### Step 5: Integrate parent history entries into import/sync workflows

**File**: `src/fluxx/jira/importer.py`

Modify the entry creation flow to avoid duplicate entries for the same issue:

**Option A (Recommended)**: Filter parents from individual processing
1. `_create_history_entries()` creates entries for non-parent issues only (exclude issues that appear as parents in hierarchy)
2. `_create_parent_history_entries()` creates entries for ALL parent issues (using own estimate or summed children per Decision 3)
3. Combine both sets of entries

**Option B**: Post-process to merge
1. `_create_history_entries()` creates entries for all done issues as before
2. `_create_parent_history_entries()` creates entries for parents needing summed estimates
3. When combining, parent entries from Step 4 override those from Step 3 for the same issue key

Option A is cleaner because each issue is processed exactly once. The hierarchy is already available, so filtering is straightforward.

In `merge_history_entries()`:
- No changes needed; deduplication by `(server_url, issue_key)` handles incremental sync correctly

### Step 6: Update tests

**Files**:
- `tests/jira/test_models.py` - Test `EstimateSource` enum and field validation
- `tests/jira/test_importer.py` - Test parent history entry creation
- `tests/data/test_migration.py` - Test 1.3→1.4 migration

Required test cases (must achieve 100% coverage):

**Model tests**:
1. `JiraDurationHistoryEntry` requires `estimate_source` field
2. Both enum values serialize/deserialize correctly

**Migration tests**:
1. Version 1.3 file migrates to 1.4 with `estimate_source` added to all entries
2. Empty history_entries list migrates without error
3. Missing jira_config migrates without error
4. Already-migrated files (with estimate_source) are unchanged

**Importer tests**:
1. Individual issue (no children) entries get `estimate_source=FROM_ORIGINAL_ESTIMATE`
2. Parent with own estimate > 0 gets entry with `estimate_source=FROM_ORIGINAL_ESTIMATE` (uses own estimate, not children's sum)
3. Parent with own estimate = 0 or None, all children closed with estimates, gets `estimate_source=FROM_SUMMING_CHILDREN`
4. Parent with some children open gets no entry
5. Parent with leaf child missing estimate gets no entry
6. Parent with intermediate child missing estimate but grandchildren have estimates: recursively computes sum
7. Multi-level hierarchy (grandchildren) sums all descendants correctly
8. `total_logged_time_seconds` is summed only when all descendants have it; else `None`
9. Parent with no children is not treated as a parent (handled by individual entry logic)

### Step 7: Verify no changes needed to distribution fitting

**File**: `src/fluxx/jira/distributions.py`

No changes required. The `estimate_source` field is stored but not used for filtering. Future models can use this field to:
- Include only `FROM_ORIGINAL_ESTIMATE` entries (conservative)
- Include only `FROM_SUMMING_CHILDREN` entries (for parent-level estimation)
- Include both (current behavior, just with the new entries added)

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/fluxx/jira/models.py` | Modify | Add `EstimateSource` enum and `estimate_source` field |
| `src/fluxx/data/migration.py` | Modify | Add 1.3→1.4 migration, update version constants |
| `src/fluxx/jira/importer.py` | Modify | Set `estimate_source`, add parent entry creation |
| `tests/jira/test_models.py` | Modify | Add tests for new enum and field |
| `tests/jira/test_importer.py` | Modify | Add tests for parent history entries |
| `tests/data/test_migration.py` | Modify | Add tests for 1.3→1.4 migration |

## Risks and Mitigations

1. **Risk**: Breaking existing `.fluxx` files
   - **Mitigation**: Migration sets default `estimate_source` on load; tested thoroughly

2. **Risk**: Performance with deeply nested hierarchies
   - **Mitigation**: Hierarchy is already built in O(n); traversal is also O(n)

3. **Risk**: Test coverage requirements not met
   - **Mitigation**: Step 6 lists comprehensive test cases covering all branches

## Important Note: No Changes to Estimation Logic

The new history entries **will be used immediately** by the existing estimation machinery - that's the purpose of this feature. Once parent tasks have history entries with estimates, the bin-based distribution fitting will automatically include them, enabling reasonable duration distributions for high-level estimates (e.g., 90-hour tasks).

What **won't be used yet** is the `estimate_source` field itself. It's stored for future applications:
- Filtering to exclude summed-children entries from models that would be corrupted by mixing estimate types
- Building specialized models for parent-level vs. leaf-level estimation
- Analyzing accuracy differences between estimate sources

No changes to simulation, sampling, or model-building code are needed.

## Out of Scope (Future Work)

- Using `estimate_source` to filter bins in distribution fitting
- UI to display estimate source in history views
- Per-bin breakdown of estimate sources
