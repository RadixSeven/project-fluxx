# MVP Jira Sync Implementation Plan

This plan implements the Jira integration specified in Section 11 of `project_fluxx_specification.md`.

## Guiding Principles

1. **TDD Throughout**: Write tests first for all non-exploratory work. Tests define the contract.
2. **Small, Focused Methods**: Each method does one thing. Easier to test, easier to maintain.
3. **Separation of Concerns**: Keep I/O (API calls) separate from logic (data transformation).
4. **Mock at Boundaries**: Prefer mocking the HTTP layer and file system, not internal functions. Exception: mocking internal functions is appropriate for testing defensive "should never happen" code paths that are difficult to trigger through normal boundaries.

---

## Phase 0: Investigation & Preparation

### 0.1 NaN Investigation for Zero-Work Tasks ✓ COMPLETE
**Goal**: Determine if `hours_logged=NaN` is safe for completed tasks with no work logged.

**Decision**: Use `1e-6`, NOT NaN.

**Findings** (see spec Section 11.7.4 for details):
- NaN bypasses Pydantic validation (`v <= 0` is False for NaN)
- NaN causes rejection sampling to exhaust max_attempts (1000 iterations)
- NaN propagates through arithmetic, corrupting simulation results
- NaN produces non-standard JSON output

### 0.2 Factor Out Auth Module from `jql.py` ✓ COMPLETE
**TDD**: Yes

**Completed**:
- Created `src/fluxx/jira/__init__.py`
- Created `src/fluxx/jira/auth.py` with `get_token_path()`, `read_token()`, `TokenNotFoundError`
- Updated `jql.py` to import from new location (re-exports for backward compatibility)
- Created `tests/jira/test_auth.py` with 11 tests
- Updated `tests/test_jql.py` to use `TokenNotFoundError`
- All 36 tests passing, 100% coverage on auth module

---

## Phase 1: Data Model Extensions

### 1.1 JiraIssueKey and JiraReference Types
**TDD**: Yes

**Tests first**:
```python
def test_jira_issue_key_valid():
    key = JiraIssueKey.from_string("FHIR-1234")
    assert key.project_key == "FHIR"
    assert key.issue_number == 1234

def test_jira_issue_key_invalid_format():
    with pytest.raises(ValidationError):
        JiraIssueKey.from_string("invalid")

def test_jira_issue_key_to_string():
    key = JiraIssueKey(project_key="FHIR", issue_number=1234)
    assert str(key) == "FHIR-1234"

def test_jira_reference_equality():
    # Same server + key = equal
    ...
```

**Implementation**:
1. Create `src/fluxx/jira/models.py`
2. Define `ProjectKey` as NewType with validator (matches `[A-Z][A-Z0-9_]+`)
3. Define `JiraIssueKey` Pydantic model with `from_string()` classmethod
4. Define `JiraReference` with `server_url` and `issue_key`

**Files**:
- `src/fluxx/jira/models.py`
- `tests/jira/test_models.py`

### 1.2 Extend Task Model
**TDD**: Yes

**Tests first**:
```python
def test_task_with_jira_reference_serializes():
    task = Task(..., jira_reference=JiraReference(...))
    data = task.model_dump()
    assert "jira_reference" in data

def test_task_without_jira_reference_allowed():
    task = Task(...)  # No jira_reference
    assert task.jira_reference is None

def test_task_jira_issue_type_optional():
    ...
```

**Implementation**:
1. Add `jira_reference: JiraReference | None = None` to Task model
2. Add `jira_issue_type: str | None = None` to Task model
3. Update Task schema version if needed

**Files**:
- `src/fluxx/data/models.py` (modify)
- `tests/test_models.py` (extend)

### 1.3 Extend Worker Model
**TDD**: Yes

**Tests first**:
```python
def test_worker_with_jira_account_id():
    worker = Worker(..., jira_account_id="abc123")
    assert worker.jira_account_id == "abc123"

def test_worker_jira_account_id_defaults_none():
    worker = Worker(...)
    assert worker.jira_account_id is None
```

**Implementation**:
1. Add `jira_account_id: str | None = None` to Worker model

**Files**:
- `src/fluxx/data/models.py` (modify)
- `tests/test_models.py` (extend)

### 1.4 JiraDurationDistribution
**TDD**: Yes

**Tests first**:
```python
def test_jira_duration_distribution_is_duration_distribution():
    dist = JiraDurationDistribution(original_estimate_seconds=3600)
    assert isinstance(dist, DurationDistribution)

def test_jira_duration_distribution_all_optional():
    dist = JiraDurationDistribution()
    assert dist.original_estimate_seconds is None
    assert dist.story_points is None
    assert dist.remaining_estimate_seconds is None
```

**Implementation**:
1. Create `JiraDurationDistribution` as subclass of `DurationDistribution`
2. Add to distribution type union

**Files**:
- `src/fluxx/data/models.py` (modify) or `src/fluxx/jira/models.py`
- `tests/jira/test_models.py` (extend)

### 1.5 JiraSyncMetadata and JiraConfig
**TDD**: Yes

**Tests first**:
```python
def test_jira_duration_history_entry_deduplication_key():
    entry = JiraDurationHistoryEntry(server_url="...", issue_key=..., ...)
    # Test that (server_url, issue_key) forms identity

def test_jira_sync_metadata_serializes():
    metadata = JiraSyncMetadata(...)
    data = metadata.model_dump()
    # Verify structure

def test_project_file_with_jira_config():
    # Test jira_config is optional and serializes correctly
    ...
```

**Implementation**:
1. Define `JiraDurationHistoryEntry` in `src/fluxx/jira/models.py`
2. Define `JiraSyncMetadata`
3. Define `JiraConfig`
4. Add `jira_config: JiraConfig | None = None` to ProjectFile model

**Files**:
- `src/fluxx/jira/models.py`
- `src/fluxx/data/models.py` (modify ProjectFile)
- `tests/jira/test_models.py`

### 1.6 File Format Migration
**TDD**: Yes

**Tests first**:
```python
def test_migrate_old_file_adds_jira_fields():
    old_data = {...}  # v1.1 format without jira fields
    new_data = migrate_to_v1_2(old_data)
    assert "jira_config" in new_data
    # Tasks should have jira_reference: None

def test_load_old_file_migrates_automatically():
    ...
```

**Implementation**:
1. Increment file format version
2. Add migration function
3. Update persistence layer

**Files**:
- `src/fluxx/data/persistence.py` (modify)
- `tests/test_persistence.py` (extend)

---

## Phase 2: Jira API Client

### 2.1 HTTP Client with Rate Limiting
**TDD**: Hybrid (explore API first, then comprehensive tests)

**Tests first** (with mocked responses):
```python
def test_client_rate_limits_requests(mocker):
    # Verify requests are spaced by rate limit interval

def test_client_retries_on_5xx(mocker):
    # First request returns 503, second succeeds

def test_client_retries_with_exponential_backoff(mocker):
    # Verify backoff timing

def test_client_respects_retry_after_header(mocker):
    # 429 with Retry-After header

def test_client_gives_up_after_max_retries(mocker):
    # Should raise after exhausting retries

def test_client_adds_bearer_token(mocker):
    # Verify Authorization header
```

**Implementation**:
1. Create `src/fluxx/jira/client.py`
2. Use `requests` with `requests_ratelimiter`
3. Use `tenacity` for retry logic with exponential backoff (max 10 min)
4. Define `JiraClient` class with:
   - `__init__(server_url: str, token: str, rate_limit: float = 1.0)`
   - `search(jql: str, fields: list[str], expand: list[str] | None = None) -> Iterator[dict]`
   - `get_issue(key: str, fields: list[str]) -> dict`
5. Handle pagination internally in `search()`

**Files**:
- `src/fluxx/jira/client.py`
- `tests/jira/test_client.py`

### 2.2 Jira API Response Parsing
**TDD**: Yes

**Tests first** (using saved JSON fixtures):
```python
def test_parse_issue_basic_fields():
    raw = load_fixture("issue_basic.json")
    issue = JiraIssueResponse.model_validate(raw)
    assert issue.key == "FHIR-1234"
    assert issue.fields.summary == "..."

def test_parse_issue_with_parent():
    raw = load_fixture("issue_with_parent.json")
    issue = JiraIssueResponse.model_validate(raw)
    assert issue.fields.parent.key == "FHIR-1000"

def test_parse_issue_links_dependencies():
    raw = load_fixture("issue_with_links.json")
    issue = JiraIssueResponse.model_validate(raw)
    depends_on = [link for link in issue.fields.issuelinks if link.type.name == "Depends"]
    assert len(depends_on) == 2

def test_parse_issue_worklogs():
    raw = load_fixture("issue_with_worklogs.json")
    issue = JiraIssueResponse.model_validate(raw)
    assert len(issue.fields.worklog.worklogs) == 3

def test_parse_issue_handles_missing_optional_fields():
    raw = load_fixture("issue_minimal.json")
    issue = JiraIssueResponse.model_validate(raw)
    assert issue.fields.customfield_10473 is None  # Story points
```

**Fixture Loading** (portable for hermetic builds):
```python
# tests/jira/conftest.py
import importlib.resources
import json

def load_fixture(name: str) -> dict:
    """Load JSON fixture using importlib.resources for portability."""
    files = importlib.resources.files("tests.jira.fixtures")
    return json.loads(files.joinpath(name).read_text())
```

**Implementation**:
1. Create `src/fluxx/jira/api_types.py`
2. Define Pydantic models for Jira API responses with `model_config = ConfigDict(extra="ignore")`:
   - `JiraIssueResponse` - top-level issue response
   - `JiraIssueFields` - the `fields` object
   - `JiraWorklog`, `JiraIssueLink`, `JiraTimeTracking`, etc.
3. These models validate external API input and provide type safety throughout
4. Use `model_validate()` to parse raw JSON dicts

**Why Pydantic for API responses**: Validating input from external sources like APIs is crucial. By defining expected semantics as Pydantic models (with `extra="ignore"` to tolerate fields we don't care about), we get:
- Runtime validation that API responses match expectations
- Type safety through the entire data pipeline
- Clear documentation of what fields we depend on
- Early failure with clear errors if Jira API changes

**Files**:
- `src/fluxx/jira/api_types.py`
- `tests/jira/test_api_types.py`
- `tests/jira/fixtures/` (JSON files, accessed via importlib.resources)
- `tests/jira/fixtures/__init__.py` (empty, makes it a package)

---

## Phase 3: Data Extraction (Jira → Fluxx)

Note: We use "extract" rather than "map" to emphasize that we're converting part of the data in a Jira structure to a different representation for a specific part of a Fluxx structure.

### 3.1 Task Completion Extraction
**TDD**: Yes

**Tests first**:
```python
def test_extract_completion_not_started_no_worklogs():
    issue = JiraIssueResponse(...)  # worklogs=[], resolution=None
    completion = extract_completion(issue, workers)
    assert isinstance(completion, NotStartedCompletion)

def test_extract_completion_not_started_with_assignee_sets_allowed_workers():
    issue = JiraIssueResponse(...)  # worklogs=[], assignee="user1"
    completion, allowed = extract_completion_and_constraints(issue, workers)
    assert allowed == [workers["user1"].id]

def test_extract_completion_started_has_worklogs_no_resolution():
    issue = JiraIssueResponse(...)  # worklogs=[...], resolution=None
    completion = extract_completion(issue, workers)
    assert isinstance(completion, StartedCompletion)
    assert completion.assignee == expected_worker_id

def test_extract_completion_done_with_work_logged():
    issue = JiraIssueResponse(...)  # worklogs=[...], resolution="Done"
    completion = extract_completion(issue, workers)
    assert isinstance(completion, DoneCompletion)
    assert completion.end_time == last_worklog_date  # Not resolution_date

def test_extract_completion_done_without_work_uses_resolution_date():
    issue = JiraIssueResponse(...)  # worklogs=[], resolution="Done"
    completion = extract_completion(issue, workers)
    assert completion.hours_logged == 1e-6  # Epsilon for zero-work tasks
    assert completion.end_time == resolution_date

def test_extract_completion_uses_assignee_or_most_worklogs():
    # Test the priority: jira_assignee > author_with_most_worklogs
    ...
```

**Implementation**:
1. Create `src/fluxx/jira/extraction.py`
2. Implement `extract_completion(issue: JiraIssueResponse, workers: dict[str, WorkerId]) -> TaskCompletion`
3. Implement logic per spec Section 11.7

**Files**:
- `src/fluxx/jira/extraction.py`
- `tests/jira/test_extraction.py`

### 3.2 Dependency Extraction
**TDD**: Yes

**Tests first**:
```python
def test_extract_dependencies_depends_on_link():
    issue = JiraIssueResponse(...)  # has "depends on" link to FHIR-100
    deps = extract_dependencies(issue, task_map)
    assert len(deps) == 1
    assert deps[0].constraint_type == ">="

def test_extract_dependencies_schedule_after_link():
    issue = JiraIssueResponse(...)  # has "schedule after" link
    deps = extract_dependencies(issue, task_map)
    # Same as depends_on

def test_extract_dependencies_skip_when_both_started():
    issue_a = JiraIssueResponse(...)  # depends on B, has worklogs
    issue_b = JiraIssueResponse(...)  # has worklogs
    deps = extract_dependencies(issue_a, task_map, started_issues={"A", "B"})
    assert len(deps) == 0  # Skipped because both started

def test_extract_dependencies_keep_when_only_one_started():
    issue_a = JiraIssueResponse(...)  # depends on B, has worklogs
    issue_b = JiraIssueResponse(...)  # no worklogs
    deps = extract_dependencies(issue_a, task_map, started_issues={"A"})
    assert len(deps) == 1  # Kept because B not started
```

**Implementation**:
1. Add to `src/fluxx/jira/extraction.py`
2. Implement `extract_dependencies()` per spec Section 11.4.4

**Files**:
- `src/fluxx/jira/extraction.py` (extend)
- `tests/jira/test_extraction.py` (extend)

### 3.3 Hierarchy Extraction
**TDD**: Yes

**Tests first**:
```python
def test_build_hierarchy_from_parent_field():
    issues = [
        JiraIssueResponse(key="EPIC-1", ...),  # no parent
        JiraIssueResponse(key="FHIR-100", ...),  # parent_key="EPIC-1"
    ]
    hierarchy = build_hierarchy(issues)
    assert hierarchy["FHIR-100"].parent == "EPIC-1"

def test_build_hierarchy_from_link_types():
    # "parent of" / "child of" links
    ...

def test_build_hierarchy_detects_sub_epic():
    issues = [
        JiraIssueResponse(key="EPIC-1", issue_type="Epic", ...),
        JiraIssueResponse(key="EPIC-2", issue_type="Epic", parent="EPIC-1", ...),
    ]
    hierarchy, warnings = build_hierarchy(issues)
    assert "EPIC-2" in warnings  # Sub-epic detected
```

**Implementation**:
1. Add to `src/fluxx/jira/extraction.py`
2. Implement `build_hierarchy()` per spec Section 11.4.3

**Files**:
- `src/fluxx/jira/extraction.py` (extend)
- `tests/jira/test_extraction.py` (extend)

### 3.4 Worker Extraction
**TDD**: Yes

**Tests first**:
```python
def test_extract_workers_from_worklogs():
    issues = [...]  # Issues with various worklog authors
    workers = extract_workers(issues)
    assert "user1" in workers
    assert workers["user1"].jira_account_id == "user1"

def test_extract_workers_from_assignees():
    # Also include assignees (not just worklog authors)
    ...

def test_calculate_hours_per_workday():
    worklogs = [
        JiraWorklog(author="user1", started=date(2024, 1, 1), timeSpentSeconds=4*3600),
        JiraWorklog(author="user1", started=date(2024, 1, 1), timeSpentSeconds=2*3600),  # Same day
        JiraWorklog(author="user1", started=date(2024, 1, 2), timeSpentSeconds=8*3600),
    ]
    hours = calculate_hours_per_workday("user1", worklogs)
    assert hours == (6 + 8) / 2  # Average of 6h and 8h days

def test_hours_per_workday_no_work_uses_average():
    # Worker with no worklogs gets average of all workers
    ...

def test_populate_allowed_workers_for_epic():
    # Workers who logged work on epic get added to epic's allowed_workers
    ...
```

**Implementation**:
1. Add to `src/fluxx/jira/extraction.py`
2. Implement `extract_workers()` and `calculate_hours_per_workday()`

**Files**:
- `src/fluxx/jira/extraction.py` (extend)
- `tests/jira/test_extraction.py` (extend)

### 3.5 Full Issue-to-Task Extraction
**TDD**: Yes

**Tests first**:
```python
def test_extract_task_from_issue():
    issue = JiraIssueResponse(...)
    task = extract_task(issue, parent_task_id, workers)
    assert task.title == issue.fields.summary
    assert task.jira_reference.issue_key.project_key == "FHIR"

def test_extract_task_preserves_description():
    ...

def test_extract_task_sets_duration_distribution():
    issue = JiraIssueResponse(...)  # has original_estimate and story_points
    task = extract_task(...)
    assert isinstance(task.duration_distribution, JiraDurationDistribution)
```

**Implementation**:
1. Add to `src/fluxx/jira/extraction.py`
2. Implement `extract_task()` combining all the above

**Files**:
- `src/fluxx/jira/extraction.py` (extend)
- `tests/jira/test_extraction.py` (extend)

---

## Phase 4: Distribution Fitting

### 4.1 Fallback Distribution Fitting
**TDD**: Yes

**Tests first**:
```python
def test_fit_fallback_distribution():
    times = [1.0, 2.0, 3.0, 5.0, 8.0, 13.0]  # Various logged times
    dist = fit_fallback_distribution(times)
    assert isinstance(dist, ShiftedLognormal)
    # Verify reasonable parameters

def test_fit_fallback_empty_raises():
    with pytest.raises(InsufficientDataError):
        fit_fallback_distribution([])

def test_fit_fallback_single_value():
    # Edge case: all same value
    ...
```

**Implementation**:
1. Create `src/fluxx/jira/distributions.py`
2. Implement `fit_fallback_distribution(times: list[float]) -> ShiftedLognormal`
3. Use scipy for lognormal fitting

**Files**:
- `src/fluxx/jira/distributions.py`
- `tests/jira/test_distributions.py`

### 4.2 Bin-Based Distribution Fitting
**TDD**: Yes

**Key Concepts**:
- A bin is "N+ elements at minimum distance from center estimate" (not "next N unique estimates")
- With ties at boundaries, count can jump significantly when moving center
- Multiple consecutive center values can produce identical bin contents
- Lower bound = 0 when bin's lowest element is dataset's lowest (no excluded element for midpoint)
- Upper bound = ∞ when bin's highest element is dataset's highest

**Example 1: Repeated estimates with center at 9 hours** (min_samples=10)

Data pairs (estimate, actual):
```
Below center's bin: [(7, 10) (7, 10) (7, 12)]
In bin (dist ≤ 1.5): [(7.5, 8) (7.5, 9) (7.5, 12) (7.5, 12) (7.75, 7) (8, 8) (8, 10) (8, 16) (8, 25) (8, 48) (9, 50)]
Above center's bin: [(11, 15) (12, 13) (12, 24) (12, 26) (14, 15)]
```

Result:
- lower_bound = 7.25 (midpoint between excluded 7 and included 7.5)
- Call: `fit_bin_distribution([8, 9, 12, 12, 7, 8, 10, 16, 25, 48, 50], lower_bound=7.25)`

Next bin centered at 11:
```
In bin (dist ≤ 3): [(8, 8) (8, 10) (8, 16) (8, 25) (8, 48) (9, 50) (11, 15) (12, 13) (12, 24) (12, 26)]
```
- lower_bound = 7.875 (midpoint between excluded 7.75 and included 8)

**Example 2: Lower bound = 0** (log space, min_samples=5)

Raw data:
```
[(0.25, 0.5) (0.5, 0.5) (0.75, 4) (1.5, 4.5) (1.5, 6) (1.5, 6) (1.75, 3.5) (2, 4) (2, 5) (2, 8) (2, 12.5) (2, 24) (3, 25)]
```

Bin centered on 0.25:
```
Contents: [(0.25, 0.5) (0.5, 0.5) (0.75, 4) (1.5, 4.5) (1.5, 6) (1.5, 6)]
dist=1.25, lower_bound=0 (0.25 is lowest estimate in dataset)
```

Bin centered on 0.5 → **same contents**, dist=1, lower_bound=0

Bin centered on 0.75 → **same contents**, dist=0.75, lower_bound=0

Bin centered on 1.5:
```
Contents: [(1.5, 4.5) (1.5, 6) (1.5, 6) (1.75, 3.5) (2, 4) (2, 5) (2, 8) (2, 12.5) (2, 24)]
dist=0.5, lower_bound=1.125 (midpoint between excluded 0.75 and included 1.5)
```

**Test Constants**: Use readable constants for log-space values:
```python
log_1_hour = math.log(3600)  # 8.188...
log_2_hours = math.log(7200)
```

**Tests first**:
```python
def test_create_bins_minimum_samples():
    data = [(est, time) for est, time in zip(estimates, times)]
    bins = create_estimate_bins(data, min_samples=30)
    for bin in bins:
        assert len(bin.samples) >= 30

def test_create_bins_single_bin_when_few_samples():
    data = [(est, time) for est, time in ...]  # < 30 samples
    bins = create_estimate_bins(data, min_samples=30)
    assert len(bins) == 1

def test_bin_bounds_are_midpoints():
    # Verify lower/upper bounds are midpoints between included/excluded
    ...

def test_lowest_bin_has_zero_lower_bound():
    ...

def test_highest_bin_has_inf_upper_bound():
    ...

def test_overlapping_bins_with_repeated_estimates():
    # Example 2 above: centers 0.25, 0.5, 0.75 all yield same bin
    data = [
        (0.25, 0.5), (0.5, 0.5), (0.75, 4), (1.5, 4.5), (1.5, 6), (1.5, 6),
        (1.75, 3.5), (2, 4), (2, 5), (2, 8), (2, 12.5), (2, 24), (3, 25)
    ]
    bins_at_025 = create_bin_centered_at(0.25, data, min_samples=5)
    bins_at_050 = create_bin_centered_at(0.5, data, min_samples=5)
    bins_at_075 = create_bin_centered_at(0.75, data, min_samples=5)
    # All three should have the same samples
    assert bins_at_025.samples == bins_at_050.samples == bins_at_075.samples
    # But different distances from center
    assert bins_at_025.max_distance == 1.25
    assert bins_at_050.max_distance == 1.0
    assert bins_at_075.max_distance == 0.75

def test_bin_with_repeated_estimates_at_boundary():
    # Example 1 above: center 9 includes many (8, *) entries
    data = [
        (7, 10), (7, 10), (7, 12),
        (7.5, 8), (7.5, 9), (7.5, 12), (7.5, 12),
        (7.75, 7),
        (8, 8), (8, 10), (8, 16), (8, 25), (8, 48),
        (9, 50),
        (11, 15), (12, 13), (12, 24), (12, 26), (14, 15)
    ]
    bin_at_9 = create_bin_centered_at(9, data, min_samples=10)
    assert bin_at_9.lower_bound == 7.25  # Midpoint between 7 and 7.5
    assert len(bin_at_9.samples) == 11

def test_find_bin_for_estimate():
    bins = [...]
    bin = find_bin_for_estimate(estimate=3600, bins=bins)
    # Should find bin whose center is closest

def test_fit_bin_distribution_allows_shift():
    # Bins with non-zero lower bound should fit with loc != 0
    bin_data = [100, 120, 150, 180]  # All positive, no values near 0
    dist = fit_bin_distribution(bin_data, lower_bound=50)
    assert dist.loc > 0  # Shifted lognormal

def test_fit_bin_distribution_zero_bound_uses_floc0():
    # Only the lowest bin (lower_bound=0) should use floc=0
    bin_data = [1, 5, 10, 20, 50]
    dist = fit_bin_distribution(bin_data, lower_bound=0)
    assert dist.loc == 0

def test_loc_monotonicity_enforced():
    # loc should increase monotonically with estimate bin center
    bins = create_estimate_bins(data, min_samples=30)
    enforce_loc_monotonicity(bins)
    for i in range(len(bins) - 1):
        assert bins[i].distribution.loc <= bins[i+1].distribution.loc

def test_sample_from_bin():
    rng = np.random.default_rng(42)
    bin = EstimateBin(...)
    samples = [bin.sample(rng) for _ in range(1000)]
    # Verify distribution looks right
```

**scipy Fitting Notes**:
- Do NOT use `floc=0` for bins whose lower bound is not 0. Bins contain data from a specific estimate range; outputs may reasonably be shifted and not include 0.
- Only use `floc=0` for the bins with (lower_bound=0) - which may not be the lowest bin depending on the distribution of times.
- After fitting all bins, enforce monotonicity: `loc` should increase or stay the same with increasing bin center estimate. Walk bins from highest to lowest and set `max_loc = min(loc, min_loc_of_larger_bins)`. If a bin's loc calcuated with no loc constraint exceeds this minimum, re-fit with `floc=min_loc_of_larger_bins`.
- You can do this in one pass if you fit the largest bins first: fit top bin unconstrained. max_loc=top_bin.loc. Now second_largest unconstrained. If second_largest.loc > max_loc, fit again with floc=max_loc. Continue down the line.
- Whether the one-pass algorithm is worth it will be up to you to evaluate once you are implementing it.

**Implementation**:
1. Add to `src/fluxx/jira/distributions.py`
2. Implement `EstimateBin` dataclass with `distribution: ShiftedLognormal`
3. Implement `fit_bin_distribution(data, lower_bound)` with proper floc handling
4. Implement `create_estimate_bins()`
5. Implement `enforce_loc_monotonicity(bins)`
6. Implement `find_bin_for_estimate()`
7. Implement `BinBasedDistributionModel` class

**Files**:
- `src/fluxx/jira/distributions.py` (extend)
- `tests/jira/test_distributions.py` (extend)

### 4.3 Integrate Distribution Fitting with Simulation
**TDD**: Yes

**Sampling API Design**:
We're sampling from a conditional distribution. The API should reflect this:
```python
# The model holds the fitted bin distributions
model = BinBasedDistributionModel(history_entries)

# JiraDurationDistribution holds the conditioning parameters
jira_params = JiraDurationDistribution(original_estimate_seconds=3600)

# Sample from the conditional distribution
rng = np.random.default_rng(seed)
sample = model.conditioned_on(jira_params).sample(rng)
```

**Tests first**:
```python
def test_conditioned_distribution_samples():
    model = BinBasedDistributionModel(history_entries)
    jira_params = JiraDurationDistribution(original_estimate_seconds=3600)
    rng = np.random.default_rng(42)
    sample = model.conditioned_on(jira_params).sample(rng)
    assert sample > 0

def test_conditioned_distribution_no_estimate_uses_fallback():
    model = BinBasedDistributionModel(history_entries)
    jira_params = JiraDurationDistribution(original_estimate_seconds=None)
    rng = np.random.default_rng(42)
    sample = model.conditioned_on(jira_params).sample(rng)
    # Should use fallback distribution
    assert sample > 0

def test_conditioned_distribution_deterministic_with_mock_rng():
    # Use mock RNG to get predictable samples for testing
    model = BinBasedDistributionModel(history_entries)
    jira_params = JiraDurationDistribution(original_estimate_seconds=3600)

    mock_rng = MockRng(returns=[0.5])  # Returns 0.5 for uniform draws
    sample = model.conditioned_on(jira_params).sample(mock_rng)
    assert sample == expected_value_for_0_5

def test_simulation_uses_conditioned_sampling():
    # Verify simulation engine correctly uses the conditional API
    ...
```

**Implementation**:
1. Implement `ConditionalDistribution` class returned by `model.conditioned_on(params)`
2. `ConditionalDistribution.sample(rng)` finds the right bin and samples
3. Integrate with simulation engine, passing through the RNG

**Files**:
- `src/fluxx/jira/distributions.py` (extend)
- `src/fluxx/simulation/engine.py` (modify to support JiraDurationDistribution)
- `tests/jira/test_distributions.py` (extend)
- `tests/test_simulation.py` (extend)

---

## Phase 5: Import Orchestration

### 5.1 Epic Import Logic
**TDD**: Yes

**Tests first**:
```python
def test_import_epic_creates_root_task():
    # Mock client
    importer = EpicImporter(client, project_file)
    result = importer.import_epic("FHIR-1234")
    assert result.root_task.title == "Epic title"
    assert result.root_task.jira_reference.issue_key == ...

def test_import_epic_creates_subtasks():
    # Epic with 5 issues
    result = importer.import_epic("FHIR-1234")
    assert len(result.tasks) == 6  # Epic + 5 issues

def test_import_epic_fetches_history():
    # Verify historical data is fetched for distribution fitting
    ...

def test_import_epic_populates_allowed_workers():
    # Epic's allowed_workers should contain workers who logged work
    ...

def test_import_epic_shows_sub_epic_warnings():
    # If sub-epic detected, include in warnings
    ...
```

**Implementation**:
1. Create `src/fluxx/jira/importer.py`
2. Implement `EpicImporter` class with `import_epic()` method
3. Orchestrate: fetch issues, fetch history, map data, create tasks

**Files**:
- `src/fluxx/jira/importer.py`
- `tests/jira/test_importer.py`

### 5.2 Sync/Update Logic
**TDD**: Yes

**Tests first**:
```python
def test_sync_updates_existing_task():
    # Task already exists with jira_reference
    # Sync should update fields, not create duplicate
    ...

def test_sync_adds_new_tasks():
    # New issue appeared in epic since last sync
    ...

def test_sync_preserves_manually_added_allowed_workers():
    # User added worker to allowed_workers manually
    # Sync should keep them
    ...

def test_sync_updates_history_for_all_projects():
    # If file has FHIR and CORE issues, update history for both
    ...

def test_sync_uses_incremental_query():
    # Should use updated >= last_sync_date
    ...
```

**Implementation**:
1. Add to `src/fluxx/jira/importer.py`
2. Implement `sync()` method with deduplication logic per spec Section 11.4.5

**Files**:
- `src/fluxx/jira/importer.py` (extend)
- `tests/jira/test_importer.py` (extend)

### 5.3 Task Linking
**TDD**: Yes

**Tests first**:
```python
def test_link_task_to_jira_valid_key():
    linker = TaskLinker(client)
    result = linker.link("FHIR-1234", existing_task)
    assert result.task.jira_reference is not None
    assert result.summary == "Issue summary for confirmation"

def test_link_task_to_jira_invalid_key():
    linker = TaskLinker(client)
    with pytest.raises(IssueNotFoundError):
        linker.link("INVALID-999", existing_task)

def test_link_task_no_server_configured():
    linker = TaskLinker(client=None)  # No server
    with pytest.raises(NoServerConfiguredError):
        linker.link("FHIR-1234", existing_task)
```

**Implementation**:
1. Add to `src/fluxx/jira/importer.py` or create `src/fluxx/jira/linker.py`
2. Implement `TaskLinker` class per spec Section 11.8

**Files**:
- `src/fluxx/jira/linker.py`
- `tests/jira/test_linker.py`

---

## Phase 6: GUI Integration

### 6.1 Import Dialog
**TDD**: Partial (use pytest-qt)

**Tests**:
```python
def test_import_dialog_shows_server_prompt_when_not_configured(qtbot):
    dialog = JiraImportDialog(project_file_without_jira)
    qtbot.addWidget(dialog)
    assert dialog.server_url_input.isVisible()

def test_import_dialog_hides_server_prompt_when_configured(qtbot):
    dialog = JiraImportDialog(project_file_with_jira)
    qtbot.addWidget(dialog)
    assert not dialog.server_url_input.isVisible()

def test_import_dialog_validates_epic_key_format(qtbot):
    ...

def test_import_dialog_shows_progress(qtbot):
    ...
```

**Implementation**:
1. Create `src/fluxx/gui/jira/import_dialog.py`
2. Implement modal dialog with:
   - Server URL input (if not configured)
   - Epic key input
   - Rate limit setting
   - Progress display

**Files**:
- `src/fluxx/gui/jira/import_dialog.py`
- `tests/gui/jira/test_import_dialog.py`

### 6.2 Jira Issue Field in Task Editor
**TDD**: Partial

**Tests**:
```python
def test_jira_field_shows_placeholder_when_none(qtbot):
    editor = TaskEditor(task_without_jira)
    assert editor.jira_field.placeholderText() == "<enter issue key>"

def test_jira_field_shows_error_when_no_server(qtbot):
    editor = TaskEditor(task, project_without_jira_config)
    assert "No Jira server configured" in editor.jira_field.text()

def test_jira_field_validates_on_focus_lost(qtbot):
    ...

def test_jira_field_loads_data_on_valid_key(qtbot):
    ...

def test_field_overwrite_warning_shown(qtbot):
    # User edits synced field, warning shown on apply
    ...
```

**Implementation**:
1. Modify `src/fluxx/gui/widgets/task_editor.py`
2. Add Jira Issue field with validation logic
3. Implement save-then-load flow per spec Section 11.8

**Files**:
- `src/fluxx/gui/widgets/task_editor.py` (modify)
- `tests/gui/test_task_editor.py` (extend)

### 6.3 Allowed Workers Field Update
**TDD**: Partial

**Tests**:
```python
def test_allowed_workers_shows_inherited(qtbot):
    # Task with no allowed_workers but ancestor has one
    editor = TaskEditor(task, project)
    assert "Inherited from" in editor.allowed_workers_display.text()

def test_allowed_workers_click_to_override(qtbot):
    ...

def test_allowed_workers_shows_all_workers_for_root(qtbot):
    ...
```

**Implementation**:
1. Modify `src/fluxx/gui/widgets/task_editor.py`
2. Update allowed workers display per spec Section 5.3.2

**Files**:
- `src/fluxx/gui/widgets/task_editor.py` (modify)
- `tests/gui/test_task_editor.py` (extend)

### 6.4 Menu Items
**TDD**: Partial

**Tests**:
```python
def test_import_from_jira_menu_item_exists(qtbot):
    window = MainWindow()
    action = window.findChild(QAction, "import_from_jira")
    assert action is not None

def test_update_from_jira_disabled_when_no_config(qtbot):
    window = MainWindow(project_without_jira)
    action = window.findChild(QAction, "update_from_jira")
    assert not action.isEnabled()

def test_update_from_jira_enabled_when_configured(qtbot):
    window = MainWindow(project_with_jira)
    action = window.findChild(QAction, "update_from_jira")
    assert action.isEnabled()
```

**Implementation**:
1. Modify `src/fluxx/gui/main_window.py`
2. Add "Import from Jira..." and "Update from Jira" menu items

**Files**:
- `src/fluxx/gui/main_window.py` (modify)
- `tests/gui/test_main_window.py` (extend)

---

## Phase 7: Integration & Polish

### 7.1 End-to-End Import Test
**TDD**: Integration test

**Test**:
```python
def test_e2e_import_epic(qtbot, mock_jira_server):
    # Full flow: open dialog, enter key, import, verify tasks created
    ...
```

### 7.2 End-to-End Sync Test
**Test**:
```python
def test_e2e_sync_updates(qtbot, mock_jira_server):
    # Import, make changes in mock server, sync, verify updates
    ...
```

### 7.3 Error Handling Polish
- Verify all error messages match spec Section 11.11
- Test network failure recovery
- Test authentication failure messages

### 7.4 Documentation
- Update CLAUDE.md if needed
- Add docstrings to all public functions/classes

### 7.5 Fix Skipped Gantt Test

**Problem**: `test_gantt_chart_with_loaded_test_prj_json` in `tests/simulation/test_real_project.py` is currently skipped because it depends on a `test_prj.json` file that was provided separately and not checked into the repository. When development moved to a different machine, the file was lost.

**Location**: `tests/simulation/test_real_project.py:513`

**Steps**:
1. Request `test_prj.json` from user (or regenerate a representative project file if the user can no longer provide it).
2. Create fixtures directory: `tests/simulation/fixtures/`
3. Add `tests/simulation/fixtures/__init__.py` (empty, makes it a package for `importlib.resources`)
4. Place `test_prj.json` in `tests/simulation/fixtures/`
5. Update test to load fixture using `importlib.resources`:
   ```python
   import importlib.resources
   import json

   def test_gantt_chart_with_loaded_test_prj_json() -> None:
       files = importlib.resources.files("tests.simulation.fixtures")
       project_data = json.loads(files.joinpath("test_prj.json").read_text())
       # ... rest of test
   ```
6. Remove the `pytest.skip()` fallback
7. Verify test passes with `QT_QPA_PLATFORM=offscreen pytest tests/simulation/test_real_project.py::test_gantt_chart_with_loaded_test_prj_json -v`

---

## Dependencies to Add

```toml
# pyproject.toml additions
[project.dependencies]
requests-ratelimiter = ">=0.4.0"
tenacity = ">=8.0.0"

[project.optional-dependencies]
dev = [
    # existing...
    "responses>=0.23.0",  # For mocking requests
]
```

---

## File Structure Summary

```
src/fluxx/jira/
├── __init__.py
├── auth.py           # Token management (factored from jql.py)
├── client.py         # HTTP client with rate limiting/retry
├── models.py         # Fluxx-side Jira models (JiraReference, JiraIssueKey, etc.)
├── api_types.py      # Pydantic models for Jira API responses (validation at boundary)
├── extraction.py     # Extract Fluxx data from Jira responses
├── distributions.py  # Bin-based distribution fitting
├── importer.py       # Epic import orchestration
└── linker.py         # Link existing tasks to Jira

src/fluxx/gui/jira/
├── __init__.py
└── import_dialog.py  # Import dialog

tests/jira/
├── __init__.py
├── fixtures/         # JSON fixtures for API responses (accessed via importlib.resources)
│   └── __init__.py   # Makes fixtures a package for importlib.resources
├── conftest.py       # load_fixture() helper using importlib.resources
├── test_auth.py
├── test_client.py
├── test_api_types.py
├── test_extraction.py
├── test_distributions.py
├── test_importer.py
└── test_linker.py

tests/gui/jira/
├── __init__.py
└── test_import_dialog.py
```

---

## Estimated Phases

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| 0 | Investigation & Preparation | None |
| 1 | Data Model Extensions | Phase 0 |
| 2 | Jira API Client | Phase 0.2 |
| 3 | Data Mapping | Phases 1, 2 |
| 4 | Distribution Fitting | Phase 1 |
| 5 | Import Orchestration | Phases 3, 4 |
| 6 | GUI Integration | Phase 5 |
| 7 | Integration & Polish | Phase 6 |

Phases 2, 3, and 4 can proceed in parallel after Phase 1 completes.
