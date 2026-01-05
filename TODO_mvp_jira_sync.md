# MVP Jira Sync Implementation Plan

This plan implements the Jira integration specified in Section 11 of `project_fluxx_specification.md`.

## Guiding Principles

1. **TDD Throughout**: Write tests first for all non-exploratory work. Tests define the contract.
2. **Small, Focused Methods**: Each method does one thing. Easier to test, easier to maintain.
3. **Separation of Concerns**: Keep I/O (API calls) separate from logic (data transformation).
4. **Mock at Boundaries**: Mock the HTTP layer, not internal functions.

---

## Phase 0: Investigation & Preparation

### 0.1 NaN Investigation for Zero-Work Tasks
**Goal**: Determine if `hours_logged=NaN` is safe for completed tasks with no work logged.

**Steps**:
1. Grep codebase for all uses of `hours_logged`
2. Trace through simulation engine to see how `hours_logged` affects:
   - Rejection sampling (duration must be >= hours_logged)
   - Any arithmetic operations
   - Serialization/deserialization
3. Check if `float('nan')` comparisons behave correctly (NaN < x is always False)
4. Document findings
5. **Decision point**: Use NaN or stick with 1e-6

**Output**: Update spec Section 11.7.4 with findings; proceed with chosen approach.

### 0.2 Factor Out Auth Module from `jql.py`
**TDD**: Yes

**Tests first**:
```python
def test_get_token_path_with_port():
    assert get_token_path("https://jira.example.com:8443/jira") == ...

def test_get_token_path_without_port():
    assert get_token_path("https://jira.example.com/jira") == ...

def test_read_token_file_not_found():
    with pytest.raises(TokenNotFoundError):
        read_token(Path("/nonexistent"))

def test_read_token_strips_whitespace():
    # Use tmp_path fixture
    ...
```

**Implementation**:
1. Create `src/fluxx/jira/__init__.py`
2. Create `src/fluxx/jira/auth.py`
3. Move `get_token_path()` and `read_token()` from `jql.py`
4. Update `jql.py` to import from new location
5. Add `TokenNotFoundError` exception class

**Files**:
- `src/fluxx/jira/auth.py`
- `tests/jira/test_auth.py`

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
    issue = parse_issue(raw)
    assert issue.key == "FHIR-1234"
    assert issue.summary == "..."

def test_parse_issue_with_parent():
    raw = load_fixture("issue_with_parent.json")
    issue = parse_issue(raw)
    assert issue.parent_key == "FHIR-1000"

def test_parse_issue_links_dependencies():
    raw = load_fixture("issue_with_links.json")
    issue = parse_issue(raw)
    assert len(issue.depends_on) == 2

def test_parse_issue_worklogs():
    raw = load_fixture("issue_with_worklogs.json")
    issue = parse_issue(raw)
    assert len(issue.worklogs) == 3

def test_parse_issue_handles_missing_optional_fields():
    raw = load_fixture("issue_minimal.json")
    issue = parse_issue(raw)
    assert issue.story_points is None
```

**Implementation**:
1. Create `src/fluxx/jira/parsing.py`
2. Define `ParsedJiraIssue` dataclass with all extracted fields
3. Define `ParsedWorklog` dataclass
4. Implement `parse_issue(raw: dict) -> ParsedJiraIssue`
5. Handle all the field mappings from spec Section 11.4.2

**Fixtures**: Save real (anonymized) Jira API responses as test fixtures.

**Files**:
- `src/fluxx/jira/parsing.py`
- `tests/jira/test_parsing.py`
- `tests/jira/fixtures/` (JSON files)

---

## Phase 3: Data Mapping (Jira → Fluxx)

### 3.1 Task Completion Mapping
**TDD**: Yes

**Tests first**:
```python
def test_map_not_started_no_worklogs():
    issue = ParsedJiraIssue(worklogs=[], resolution=None, ...)
    completion = map_completion(issue)
    assert isinstance(completion, NotStartedCompletion)

def test_map_not_started_with_assignee_sets_allowed_workers():
    issue = ParsedJiraIssue(worklogs=[], assignee="user1", ...)
    completion, allowed = map_completion_and_constraints(issue)
    assert allowed == ["user1"]

def test_map_started_has_worklogs_no_resolution():
    issue = ParsedJiraIssue(worklogs=[...], resolution=None, ...)
    completion = map_completion(issue)
    assert isinstance(completion, StartedCompletion)
    assert completion.assignee == expected_worker_id

def test_map_done_with_work_logged():
    issue = ParsedJiraIssue(worklogs=[...], resolution="Done", ...)
    completion = map_completion(issue)
    assert isinstance(completion, DoneCompletion)
    assert completion.end_time == last_worklog_date  # Not resolution_date

def test_map_done_without_work_uses_resolution_date():
    issue = ParsedJiraIssue(worklogs=[], resolution="Done", ...)
    completion = map_completion(issue)
    assert completion.hours_logged == 1e-6  # Or NaN per investigation
    assert completion.end_time == resolution_date

def test_map_started_uses_assignee_or_most_worklogs():
    # Test the priority: jira_assignee > author_with_most_worklogs
    ...
```

**Implementation**:
1. Create `src/fluxx/jira/mapping.py`
2. Implement `map_completion(issue: ParsedJiraIssue, workers: dict[str, WorkerId]) -> TaskCompletion`
3. Implement logic per spec Section 11.7

**Files**:
- `src/fluxx/jira/mapping.py`
- `tests/jira/test_mapping.py`

### 3.2 Dependency Mapping
**TDD**: Yes

**Tests first**:
```python
def test_map_depends_on_link():
    issue = ParsedJiraIssue(depends_on=["FHIR-100"], ...)
    deps = map_dependencies(issue, task_map)
    assert len(deps) == 1
    assert deps[0].constraint_type == ">="

def test_map_schedule_after_link():
    issue = ParsedJiraIssue(schedule_after=["FHIR-100"], ...)
    deps = map_dependencies(issue, task_map)
    # Same as depends_on

def test_skip_dependency_when_both_started():
    issue_a = ParsedJiraIssue(key="A", depends_on=["B"], worklogs=[...])
    issue_b = ParsedJiraIssue(key="B", worklogs=[...])
    deps = map_dependencies(issue_a, task_map, started_issues={"A", "B"})
    assert len(deps) == 0  # Skipped because both started

def test_keep_dependency_when_only_one_started():
    issue_a = ParsedJiraIssue(key="A", depends_on=["B"], worklogs=[...])
    issue_b = ParsedJiraIssue(key="B", worklogs=[])
    deps = map_dependencies(issue_a, task_map, started_issues={"A"})
    assert len(deps) == 1  # Kept because B not started
```

**Implementation**:
1. Add to `src/fluxx/jira/mapping.py`
2. Implement `map_dependencies()` per spec Section 11.4.4

**Files**:
- `src/fluxx/jira/mapping.py` (extend)
- `tests/jira/test_mapping.py` (extend)

### 3.3 Hierarchy Mapping
**TDD**: Yes

**Tests first**:
```python
def test_map_parent_child_from_parent_field():
    issues = [
        ParsedJiraIssue(key="EPIC-1", parent_key=None),
        ParsedJiraIssue(key="FHIR-100", parent_key="EPIC-1"),
    ]
    hierarchy = build_hierarchy(issues)
    assert hierarchy["FHIR-100"].parent == "EPIC-1"

def test_map_parent_child_from_link_types():
    # "parent of" / "child of" links
    ...

def test_detect_sub_epic_warning():
    issues = [
        ParsedJiraIssue(key="EPIC-1", issue_type="Epic"),
        ParsedJiraIssue(key="EPIC-2", issue_type="Epic", parent_key="EPIC-1"),
    ]
    hierarchy, warnings = build_hierarchy(issues)
    assert "EPIC-2" in warnings  # Sub-epic detected
```

**Implementation**:
1. Add to `src/fluxx/jira/mapping.py`
2. Implement `build_hierarchy()` per spec Section 11.4.3

**Files**:
- `src/fluxx/jira/mapping.py` (extend)
- `tests/jira/test_mapping.py` (extend)

### 3.4 Worker Mapping
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
        Worklog(author="user1", date=date(2024, 1, 1), seconds=4*3600),
        Worklog(author="user1", date=date(2024, 1, 1), seconds=2*3600),  # Same day
        Worklog(author="user1", date=date(2024, 1, 2), seconds=8*3600),
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
1. Add to `src/fluxx/jira/mapping.py`
2. Implement `extract_workers()` and `calculate_hours_per_workday()`

**Files**:
- `src/fluxx/jira/mapping.py` (extend)
- `tests/jira/test_mapping.py` (extend)

### 3.5 Full Issue-to-Task Mapping
**TDD**: Yes

**Tests first**:
```python
def test_map_issue_to_task():
    issue = ParsedJiraIssue(...)
    task = map_issue_to_task(issue, parent_task_id, workers)
    assert task.title == issue.summary
    assert task.jira_reference.issue_key.project_key == "FHIR"

def test_map_issue_preserves_description():
    ...

def test_map_issue_sets_duration_distribution():
    issue = ParsedJiraIssue(original_estimate=3600, story_points=5, ...)
    task = map_issue_to_task(...)
    assert isinstance(task.duration_distribution, JiraDurationDistribution)
```

**Implementation**:
1. Add to `src/fluxx/jira/mapping.py`
2. Implement `map_issue_to_task()` combining all the above

**Files**:
- `src/fluxx/jira/mapping.py` (extend)
- `tests/jira/test_mapping.py` (extend)

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

def test_find_bin_for_estimate():
    bins = [...]
    bin = find_bin_for_estimate(estimate=3600, bins=bins)
    # Should find bin whose center is closest

def test_sample_from_bin():
    bin = EstimateBin(...)
    samples = [bin.sample() for _ in range(1000)]
    # Verify distribution looks right
```

**Implementation**:
1. Add to `src/fluxx/jira/distributions.py`
2. Implement `EstimateBin` dataclass
3. Implement `create_estimate_bins()`
4. Implement `find_bin_for_estimate()`
5. Implement `BinBasedDistributionModel` class

**Files**:
- `src/fluxx/jira/distributions.py` (extend)
- `tests/jira/test_distributions.py` (extend)

### 4.3 Integrate Distribution Fitting with Simulation
**TDD**: Yes

**Tests first**:
```python
def test_jira_duration_distribution_samples():
    dist = JiraDurationDistribution(original_estimate_seconds=3600)
    model = BinBasedDistributionModel(history_entries)
    sample = dist.sample(model)
    assert sample > 0

def test_jira_duration_distribution_no_estimate_uses_fallback():
    dist = JiraDurationDistribution(original_estimate_seconds=None)
    model = BinBasedDistributionModel(history_entries)
    sample = dist.sample(model)
    # Should use fallback distribution
```

**Implementation**:
1. Add `sample()` method to `JiraDurationDistribution`
2. Integrate with simulation engine

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
├── models.py         # Jira-specific Pydantic models
├── parsing.py        # Parse Jira API responses
├── mapping.py        # Map Jira data to Fluxx models
├── distributions.py  # Bin-based distribution fitting
├── importer.py       # Epic import orchestration
└── linker.py         # Link existing tasks to Jira

src/fluxx/gui/jira/
├── __init__.py
└── import_dialog.py  # Import dialog

tests/jira/
├── __init__.py
├── fixtures/         # JSON fixtures for API responses
├── test_auth.py
├── test_client.py
├── test_parsing.py
├── test_mapping.py
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
