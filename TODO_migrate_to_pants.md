# Migration Plan: Use Pants for Incremental Testing

## Goal

Use Pants **only for running tests** to enable:
- **Incremental testing**: Only run tests affected by changed files
- **Cached results**: Skip tests whose inputs haven't changed

Everything else (linting, type checking, coverage verification, running the app) stays with the existing make/pip workflow.

## Scope

| Task | Tool | Environment |
|------|------|-------------|
| Running tests | Pants | Pants-managed (hermetic) |
| Coverage generation | Pants (`--test-use-coverage`) | Pants-managed (hermetic) |
| Coverage verification (90% GUI, 100% other) | make (reads Pants output) | venv |
| Linting (ruff) | make (existing) | venv |
| Type checking (mypy) | make (existing) | venv |
| Running the application | `fluxx` (existing) | venv |
| Dependency management | pip + pyproject.toml (existing) | venv |

Pants uses its own hermetic environment for testing, which provides:
- Reproducible test runs across machines
- Isolation from local venv state
- Foundation for migrating more functionality to Pants later

## Prerequisites

- [x] Pants executable installed in `bin/`
- [x] Wrapper script `./pants` in repo root

## Migration Steps

### Phase 1: Bootstrap Pants Configuration

1. **Create `pants.toml`** (config for hermetic testing)
   ```toml
   [GLOBAL]
   pants_version = "2.24.0"
   backend_packages = [
       "pants.backend.python",
   ]

   [source]
   root_patterns = ["/src", "/tests", "/stubs"]

   [python]
   interpreter_constraints = ["CPython>=3.13"]
   enable_resolves = true
   default_resolve = "default"

   [python.resolves]
   default = "locks/default.lock"

   [pytest]
   args = ["--no-header", "-vv"]
   env_vars = ["QT_QPA_PLATFORM=offscreen"]
   execution_slot_var = "TEST_EXECUTION_SLOT"

   [coverage-py]
   report = ["json"]
   ```

   Coverage data will be written to `dist/coverage/python/coverage.json` when tests are run with `--test-use-coverage`.

2. **Run initial bootstrap**
   ```bash
   ./pants --version  # Downloads pants, verifies setup
   ```

### Phase 2: Create BUILD Files

Pants requires `BUILD` files to define targets. Create minimal files for source and test discovery.

3. **Create `src/fluxx/BUILD`**
   ```python
   python_sources()
   ```

4. **Create BUILD files for source subdirectories**
   - `src/fluxx/data/BUILD`
   - `src/fluxx/simulation/BUILD`
   - `src/fluxx/gui/BUILD`
   - `src/fluxx/gui/panels/BUILD`
   - `src/fluxx/gui/widgets/BUILD`
   - `src/fluxx/gui/widgets/editors/BUILD`
   - `src/fluxx/gui/widgets/dag_view/BUILD`
   - `src/fluxx/gui/widgets/list_view/BUILD`
   - `src/fluxx/gui/simulation/BUILD`
   - `src/fluxx/gui/jira/BUILD`
   - `src/fluxx/gui/utils/BUILD`
   - `src/fluxx/jira/BUILD`
   - `src/fluxx/visualization/BUILD`

   Each containing:
   ```python
   python_sources()
   ```

5. **Create `stubs/BUILD`** (and subdirectories as needed)
   ```python
   python_sources()
   ```

   The `stubs/` directory contains mypy type stubs. Create additional BUILD files in subdirectories if they exist, each containing `python_sources()`.

6. **Create `tests/BUILD`**
   ```python
   python_tests()
   ```

7. **Create BUILD files for test subdirectories**

   Test directories (containing `test_*.py` files):
   - `tests/simulation/BUILD`
   - `tests/gui/BUILD`
   - `tests/gui/simulation/BUILD`
   - `tests/gui/jira/BUILD`
   - `tests/jira/BUILD`

   Each containing:
   ```python
   python_tests()
   ```

   Fixtures directories (containing helper modules/data, not tests):
   - `tests/simulation/fixtures/BUILD`
   - `tests/jira/fixtures/BUILD`

   Each containing:
   ```python
   python_sources()
   ```

8. **Create `BUILD`** in repo root (reads dependencies from pyproject.toml)
   ```python
   python_requirements(
       name="reqs",
       source="pyproject.toml",
   )
   ```

   Pants will parse both `[project.dependencies]` and `[project.optional-dependencies.dev]` automatically.

### Phase 3: Generate Lock File

9. **Create locks directory**
   ```bash
   mkdir -p locks
   ```

10. **Generate the lock file**
    ```bash
    ./pants generate-lockfiles
    ```
    This creates `locks/default.lock` with pinned dependencies for hermetic builds.

### Phase 4: Verify Basic Functionality

11. **Run a single test file**
    ```bash
    ./pants test tests/test_models.py
    ```

12. **Run all tests**
    ```bash
    ./pants test ::
    ```

13. **Run tests for a specific module**
    ```bash
    ./pants test tests/simulation::
    ```

### Phase 5: Test Incremental Behavior

14. **Verify caching works**
    ```bash
    # First run - executes all tests
    ./pants test ::

    # Second run (no changes) - should report all cached
    ./pants test ::
    # Expected output: tests are skipped with "memoized" status
    ```

15. **Verify incremental runs**
    ```bash
    # Run all tests
    ./pants test ::

    # Make a small change to a source file
    # (manually edit src/fluxx/data/models.py)

    # Run tests again - should only run tests that depend on models.py
    ./pants test ::
    ```

### Phase 6: Update Workflow

16. **Add Pants cache directories to `.gitignore`**
    ```
    # Pants
    .pants.d/
    .pids/
    dist/
    ```

    Note: `locks/` should be **committed** to version control to ensure reproducible builds across machines.

17. **Update CLAUDE.md** with pants test commands:
    ```markdown
    ### Running Tests with Pants (incremental)
    ./pants test ::                  # All tests
    ./pants test tests/test_models.py  # Single file
    ./pants test tests/simulation::    # Module
    ```

18. **You (human) update make `test` target** to call pants instead of pytest directly

19. **You (human) update make coverage targets** to use Pants coverage output
    - Run tests with coverage: `./pants test --test-use-coverage ::`
    - Coverage JSON is written to `dist/coverage/python/coverage.json`
    - Update `make coverage` and `make verify-coverage` to read from this location

## Commands After Migration

```bash
# Incremental test run (Pants - uses hermetic environment)
./pants test ::

# Run specific tests
./pants test tests/test_models.py
./pants test tests/simulation::

# Run tests with coverage (generates dist/coverage/python/coverage.json)
./pants test --test-use-coverage ::

# Full validation with coverage (make - reads Pants coverage output)
make all_checks

# Run the app (unchanged, uses venv)
. venv/bin/activate && fluxx
```

## Expected Benefits

| Scenario | Before | After |
|----------|--------|-------|
| Run tests after small change | All tests run (~minutes) | Only affected tests run |
| Run tests twice (no changes) | All tests run | Instant (cached) |
| Run tests on unrelated file change | All tests run | No tests run |

## What Stays the Same

- `make all_checks` for full validation
- Coverage thresholds enforced by make (90% GUI, 100% other) - now reads from Pants coverage output
- Linting and formatting via make/ruff (uses venv)
- Type checking via make/mypy (uses venv)
- Running `fluxx` and other entry points from venv
- `pip install -e ".[dev]"` for development install
- Pre-commit hooks

## Validation Checklist

- [ ] `./pants test ::` passes all tests
- [ ] Lock file generated and committed successfully
- [ ] Second run with no changes is instant (cached)
- [ ] Changes to source files trigger only dependent tests
- [ ] `./pants test --test-use-coverage ::` generates `dist/coverage/python/coverage.json`
- [ ] `make all_checks` still works for full validation (reads Pants coverage output)

## Rollback Plan

If Pants causes issues:
1. Remove `pants.toml` and all `BUILD` files
2. Remove `locks/` directory (and remove from git)
3. Remove `.pants.d/`, `.pids/`, and `dist/` directories
4. Remove Pants entries from `.gitignore`
5. Revert make test and coverage targets to call pytest directly

## Keeping Dependencies in Sync

When you update `pyproject.toml` dependencies, regenerate the lock file:
```bash
./pants generate-lockfiles
```

No separate requirements file to maintain - Pants reads directly from `pyproject.toml`.

## References

- [Pants Python Backend](https://www.pantsbuild.org/docs/python)
- [Pants + pytest](https://www.pantsbuild.org/docs/python-test-goal)
- [Pants Lockfiles](https://www.pantsbuild.org/docs/python-lockfiles)
