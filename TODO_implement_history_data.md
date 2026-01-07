# TODO: Implement Jira Duration History Data Collection and Storage

## Summary

The system should download `JiraDurationHistoryEntry` objects for all completed tickets in referenced Jira projects (e.g., `project=CORE` for CORE-123) and save them to the fluxx file. This historical data is then used for bin-based duration distribution fitting.

Currently:
- History entries ARE created during import (via `_create_history_entries()`)
- History entries are only collected from the **import scope** (epic + children), not all project tickets
- History entries are **NOT saved** to the fluxx file (the data is discarded)
- The "Update from Jira" operation does not sync history data

## Root Cause Analysis

### Problem 1: History only collected from import scope

In `importer.py:661-663`, history entries are created only from issues matching the JQL:
```python
history_entries = _create_history_entries(
    issues, workers, config.server_url, config.server_timezone
)
```
There is no separate query for all completed issues in the project.

### Problem 2: History entries not saved

In `import_dialog.py:271-275`, `JiraConfig` is created with empty history:
```python
sync_metadata=JiraSyncMetadata(
    server_url=server_url,
    last_history_sync=datetime.now(UTC),
    history_entries=[],  # Always empty!
),
```

In `main_window.py:596-600`, `result.history_entries` is ignored:
```python
def on_import_completed(result: ImportResult) -> None:
    self.controller._project = result.project  # history_entries not used
```

### Problem 3: Sync does not update history

The `sync_from_jira()` function in `importer.py` does not fetch or update history entries.

---

## Specification Requirements (from project_fluxx_specification.md)

### Section 11.3.4 - Sync Behavior Notes

> - The set of Jira project keys to sync is derived dynamically by iterating over all tasks with `jira_reference` and collecting the distinct `project_key` values.
> - A single `last_history_sync` timestamp is shared across all projects. When "Update from Jira" runs, historical data for all referenced projects is refreshed.
> - Only tasks with an explicit `jira_reference` are synchronized.

### Section 11.4.3 - JQL Queries

```
# Get historical data for distribution fitting (all completed issues in project)
project = {project_key} AND resolution in ("Complete", "Fixed", "Not a bug", "Done", "Cannot Reproduce") AND updated >= "{last_sync_date}"
```

### Section 11.5.1 - Historical Data Collection

> **Incremental Sync**: A single `last_history_sync` timestamp tracks when history was last fetched. On subsequent syncs, query only issues with `updated >= last_sync_date` for all referenced projects. The first sync when adding any new project will sync all its issues.

---

## Tasks

### Phase 1: Add Project Key Extraction

#### 1.1 Add helper function to collect distinct project keys

Create a function to extract all distinct Jira project keys from tasks with `jira_reference`.

- [ ] Add `collect_jira_project_keys(project: Project) -> set[str]` to `importer.py`
- [ ] Extract `project_key` from each task's `jira_reference.issue_key.project_key`
- [ ] Return set of unique project keys

**File**: `src/fluxx/jira/importer.py`

### Phase 2: Implement History Fetching

#### 2.1 Add JQL builder for historical data

Create a function to build the JQL query for fetching completed issues.

- [ ] Add `build_history_jql(project_keys: set[str], last_sync: datetime | None) -> str`
- [ ] Query pattern: `project in (...) AND resolution in ("Complete", "Fixed", "Not a bug", "Done", "Cannot Reproduce")`
- [ ] Add `AND updated >= "{last_sync_date}"` clause if `last_sync` is provided
- [ ] Format datetime as Jira-compatible string (e.g., "2024-01-15 00:00")

**File**: `src/fluxx/jira/importer.py`

#### 2.2 Add function to fetch history entries from Jira

Create a function that fetches completed issues and creates history entries.

- [ ] Add `fetch_history_entries(client: JiraClient, project_keys: set[str], last_sync: datetime | None, server_url: str, server_timezone: str) -> list[JiraDurationHistoryEntry]`
- [ ] Use `build_history_jql()` to construct query
- [ ] Fetch issues using client.search()
- [ ] Create `JiraDurationHistoryEntry` for each completed issue
- [ ] Include issues from ALL referenced projects, not just the import scope

**File**: `src/fluxx/jira/importer.py`

#### 2.3 Add history merge/deduplication logic

Create a function to merge new history entries with existing ones.

- [ ] Add `merge_history_entries(existing: list[JiraDurationHistoryEntry], new: list[JiraDurationHistoryEntry]) -> list[JiraDurationHistoryEntry]`
- [ ] Deduplicate by `(server_url, issue_key)` tuple
- [ ] New entries replace existing entries for the same issue (handles updates)
- [ ] Preserve existing entries not in the new set (handles deleted issues gracefully)

**File**: `src/fluxx/jira/importer.py`

### Phase 3: Update Import Flow

#### 3.1 Modify import_from_jira to fetch project-wide history

Update the import function to fetch history for all completed issues in referenced projects.

- [ ] After fetching epic issues, determine project key(s) from the imported issues
- [ ] Call `fetch_history_entries()` to get all completed issues from those projects
- [ ] Create history entries from the full project data, not just the import scope
- [ ] Include history entries in the returned `ImportResult`

**File**: `src/fluxx/jira/importer.py`

#### 3.2 Update import dialog to pass history entries to project

Ensure history entries are attached to the project's `jira_config`.

- [ ] In `_run_import()`, after getting `ImportResult`:
  - Create `JiraSyncMetadata` with the fetched `history_entries`
  - Update the returned project's `jira_config` with the populated sync_metadata
- [ ] Or: modify `_build_project()` in importer.py to accept and store history entries

**File**: `src/fluxx/gui/jira/import_dialog.py` or `src/fluxx/jira/importer.py`

#### 3.3 Update main_window handler to use project with history

Ensure the project emitted from import includes the history data.

- [ ] Verify `result.project.jira_config.sync_metadata.history_entries` is populated
- [ ] The current handler already uses `result.project`, so no changes needed if Phase 3.2 is done correctly

**File**: `src/fluxx/gui/main_window.py` (verify, may not need changes)

### Phase 4: Update Sync Flow

#### 4.1 Modify sync_from_jira to refresh history

Update the sync function to fetch and merge history entries.

- [ ] Add history sync phase after task sync:
  1. Collect all project keys from synced tasks
  2. Get `last_history_sync` from existing `sync_metadata`
  3. Fetch new/updated history entries since last sync
  4. Merge with existing history entries
  5. Update `last_history_sync` timestamp
- [ ] Update `SyncResult` to include updated `jira_config` with new history
- [ ] Consider: Add `history_entries_added: int` to `SyncResult` for UI feedback

**File**: `src/fluxx/jira/importer.py`

#### 4.2 Update sync dialog to persist history

Ensure synced history is saved to the project.

- [ ] In `_run_sync()`, ensure the returned project has updated `jira_config`
- [ ] The `sync_completed` signal should emit a project with the new history

**File**: `src/fluxx/gui/jira/sync_dialog.py`

#### 4.3 Update main_window sync handler

Ensure the sync result updates the project correctly.

- [ ] Verify `_on_update_from_jira()` uses `result.project` which includes updated `jira_config`
- [ ] May need to add success message showing history entries synced

**File**: `src/fluxx/gui/main_window.py`

### Phase 5: Use Full History for Distribution Fitting

#### 5.1 Modify import to use project-wide history for bins

Update distribution fitting to use all history, not just import scope.

- [ ] In `import_from_jira()`, after fetching project-wide history:
  - Use `extract_raw_estimate_data(history_entries)` with the FULL history
  - Create bins using the full historical data
  - Apply distributions to imported tasks
- [ ] This ensures newly imported tasks benefit from all project history

**File**: `src/fluxx/jira/importer.py`

#### 5.2 Consider: Add re-fit distributions on sync

Optionally, when syncing:
- [ ] If new history entries were added, re-fit duration distributions
- [ ] Update tasks that still have `JiraDurationDistribution` (unresolved)
- [ ] This is a "nice to have" - may defer to future work

**File**: `src/fluxx/jira/importer.py` (optional)

### Phase 6: Add Tests

#### 6.1 Test history fetching

- [ ] Test `collect_jira_project_keys()` extracts correct keys
- [ ] Test `build_history_jql()` generates correct JQL
  - Without last_sync date (first import)
  - With last_sync date (incremental sync)
- [ ] Test `fetch_history_entries()` creates correct entries
- [ ] Test `merge_history_entries()` deduplication and updates

**File**: `tests/jira/test_importer.py`

#### 6.2 Test import with history persistence

- [ ] Test that imported project has `jira_config.sync_metadata.history_entries` populated
- [ ] Test that history includes all completed issues in project, not just imported epic
- [ ] Test that `last_history_sync` is set correctly

**File**: `tests/jira/test_importer.py`

#### 6.3 Test sync updates history

- [ ] Test that sync fetches new history entries since last sync
- [ ] Test that history is merged correctly (new entries added, existing updated)
- [ ] Test that `last_history_sync` is updated after sync
- [ ] Test incremental sync only fetches updated issues

**File**: `tests/jira/test_importer.py`

#### 6.4 Test distribution fitting uses full history

- [ ] Test that bins are created from project-wide history
- [ ] Test that imported tasks get distributions based on full history
- [ ] Test fallback distribution uses full history

**File**: `tests/jira/test_importer.py`

#### 6.5 GUI tests

- [ ] Test import dialog produces project with history
- [ ] Test sync dialog updates project with new history
- [ ] Test history count appears in sync success message (if implemented)

**Files**: `tests/gui/jira/test_import_dialog.py`, `tests/gui/jira/test_sync_dialog.py`

---

## Implementation Notes

### JQL Date Format

Jira JQL expects dates in format: `"2024-01-15"` or `"2024-01-15 14:30"`. Python datetime should be formatted as:
```python
last_sync.strftime("%Y-%m-%d %H:%M")
```

### History Entry Deduplication Key

Use `(server_url, str(issue_key))` as the deduplication key. The `JiraIssueKey` model's `__str__` method returns `"PROJECT-123"` format.

### Incremental vs Full Sync

- **First import/sync**: No `last_history_sync` exists, fetch ALL completed issues
- **Subsequent syncs**: Use `updated >= last_sync_date` to fetch only changed issues
- **Merge strategy**: New entries override existing entries for same issue key

### Performance Considerations

Per spec section 11.3.4:
> The set of Jira project keys to sync is derived dynamically by iterating over all tasks with `jira_reference` and collecting the distinct `project_key` values. This is effectively instant even for large files (<100K issues).

The history fetch may return many issues, but:
- We only request necessary fields
- Incremental sync limits results after first import
- History entries are compact (no full issue data stored)

### Resolution Values

From spec section 11.4.3, completed issues have:
```
resolution in ("Complete", "Fixed", "Not a bug", "Done", "Cannot Reproduce")
```

---

## Testing Checklist

- [ ] Import from Jira creates project with history entries
- [ ] History includes all completed issues in referenced projects
- [ ] `last_history_sync` timestamp is recorded
- [ ] Sync updates history entries incrementally
- [ ] Distribution fitting uses full project history
- [ ] Imported tasks get distributions based on historical data
- [ ] Existing tests still pass
- [ ] 100% test coverage maintained for non-GUI code
- [ ] 90%+ test coverage for GUI code

---

## Related Files

- `src/fluxx/jira/importer.py` - Main import/sync logic
- `src/fluxx/jira/models.py` - JiraDurationHistoryEntry, JiraSyncMetadata models
- `src/fluxx/jira/distributions.py` - Bin-based distribution fitting
- `src/fluxx/gui/jira/import_dialog.py` - Import UI
- `src/fluxx/gui/jira/sync_dialog.py` - Sync UI
- `src/fluxx/gui/main_window.py` - Main window handlers
- `project_fluxx_specification.md` - Sections 11.3.4, 11.4.3, 11.5.1
