# TODO: Fix Jira Data Center Compatibility Bug

## Summary

The Jira import fails because the code assumes Jira Cloud's `accountId` user identification, but Project Fluxx targets **Jira Data Center** (per spec section 11.1). Jira Data Center uses `name` and `key` fields for user identification instead.

## Root Cause

In `src/fluxx/jira/api_types.py:16`, `JiraUser` requires `accountId`:
```python
account_id: str = Field(alias="accountId")
```

Jira Data Center returns user objects with `name` and `key` instead.

---

## Tasks

### 1. Fix JiraUser Model (api_types.py)

- [ ] Make `account_id` optional in `JiraUser`
- [ ] Add `name: str | None` field (Jira Data Center primary identifier)
- [ ] Add `key: str | None` field (Jira Data Center alternate identifier)
- [ ] Add a helper method or property to get the user identifier (prefer `accountId` for Cloud, fall back to `name` or `key` for Data Center)

**File**: `src/fluxx/jira/api_types.py`

### 2. Update Worker Extraction (extraction.py)

The following functions use `account_id` directly and need to use the new user identifier helper:

- [ ] `_get_worker_logged_seconds()` (line 135) - uses `w.author.account_id`
- [ ] `_get_assignee_worker_id()` (line 203) - uses `issue.fields.assignee.account_id`
- [ ] `_extract_not_started()` (line 224) - uses `issue.fields.assignee.account_id`
- [ ] `extract_workers_with_no_hours()` (lines 537, 549) - uses `account_id` for worker dict keys
- [ ] `calculate_hours_per_workday()` (line 575) - filters by `account_id`

**File**: `src/fluxx/jira/extraction.py`

### 3. Update Import History Creation (importer.py)

- [ ] `_create_history_entries()` (line 338) - uses `wlog.author.account_id`

**File**: `src/fluxx/jira/importer.py`

### 4. Rename Worker.jira_account_id to jira_user_id

The field `jira_account_id` on the Worker model (line 263 in `data/models.py`) is misleadingly named since Data Center doesn't use account IDs. Rename to `jira_user_id`.

- [ ] Rename field from `jira_account_id` to `jira_user_id`
- [ ] Update docstring to clarify it stores the Jira user identifier (name for Data Center, accountId for Cloud)

**File**: `src/fluxx/data/models.py`

### 5. Rename JiraDurationHistoryEntry.worker_jira_id

Update the `worker_jira_id` field (line 128-129 in `jira/models.py`) docstring.

- [ ] Update docstring to clarify it stores the user identifier (name for Data Center, accountId for Cloud)

**File**: `src/fluxx/jira/models.py`

### 6. Add File Format Migration (1.2 → 1.3)

Since we're renaming `jira_account_id` to `jira_user_id`, we need a file format migration.

- [ ] Bump file version to 1.3
- [ ] Add migration function in `migration.py` to rename `jira_account_id` → `jira_user_id` in Worker objects

**File**: `src/fluxx/data/migration.py`

### 7. Update Tests

- [ ] Update test fixtures that create mock `JiraUser` objects to include both Cloud-style (`accountId`) and Data Center-style (`name`/`key`) user objects
- [ ] Add specific tests for Data Center user identification
- [ ] Ensure tests cover the fallback logic when `accountId` is missing

**Files**: `tests/test_jira_*.py`

### 8. Update Specification

- [ ] Update section 11.1 to explicitly state: "Project Fluxx is compatible with Jira Data Center. Jira Cloud compatibility is a future enhancement."
- [ ] Update section 11.3.2 (Worker Jira Reference) to document that the identifier may be `accountId` (Cloud), `name`, or `key` (Data Center)

**File**: `project_fluxx_specification.md`

---

## Implementation Notes

### User Identifier Resolution Strategy

When extracting a user identifier from a `JiraUser` object, use this priority:
1. `name` (Jira Data Center primary) - if present and non-empty
2. `accountId` (Jira Cloud) - if present and non-empty
3. `key` (Jira Data Center alternate) - if present and non-empty

This prioritizes Data Center (our primary target) while maintaining Cloud compatibility as a future enhancement.

### Migration Considerations

File format migration (1.2 → 1.3) will:
- Rename `jira_account_id` to `jira_user_id` in Worker objects
- Existing `.fluxx` files will be automatically migrated on load
- The stored identifier values remain unchanged (just the field name changes)

---

## Testing Checklist

- [ ] Import from Jira Data Center succeeds (FHIR-3323 test case)
- [ ] Worklogs are correctly attributed to workers
- [ ] Worker hours per workday calculation works
- [ ] Completion status extraction works
- [ ] Existing tests still pass
- [ ] 100% test coverage maintained

---

## Related Files

- `BUG-failed-import-from-fhir-3323.md` - Original bug report
- `failed-import-from-fhir-3323.png` - Screenshot of the error
