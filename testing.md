# Testing Guidelines for LLMs

This document provides guidance for LLMs writing or modifying tests in this codebase.

## Running Tests

Always use the virtual environment and set the Qt platform for headless testing:

```bash
source venv/bin/activate
QT_QPA_PLATFORM=offscreen pytest tests/path/to/test.py -v
```

For full validation including type checking:

```bash
source venv/bin/activate && make all_checks
```

## GUI Testing with pytest-qt

GUI tests use `pytest-qt`. The `qtbot` fixture manages widget lifecycle:

```python
def test_widget_behavior(qtbot: "QtBot") -> None:
    widget = MyWidget()
    qtbot.addWidget(widget)  # Ensures proper cleanup

    # Simulate interactions
    qtbot.mouseClick(widget.button, Qt.LeftButton)

    assert widget.state == expected
```

## Mocking Patterns

### Mocking Dialogs

Qt dialogs (QMessageBox, QInputDialog, QFileDialog) block execution. Mock them at the module level where they're used:

```python
def test_with_dialog(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock QInputDialog.getText to return a value
    mock_dialog = MagicMock(return_value=("User Input", True))
    monkeypatch.setattr("fluxx.gui.main_window.QInputDialog.getText", mock_dialog)

    window._on_new_task()

    mock_dialog.assert_called_once()
```

### Mocking Instance Methods

For testing exception handling paths, mock methods on instances:

```python
def test_exception_handling(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock to raise exception
    mock_save = MagicMock(side_effect=Exception("Save failed"))
    monkeypatch.setattr(window.controller, "save_project", mock_save)

    # Mock error display to capture call
    mock_show_error = MagicMock()
    monkeypatch.setattr(window, "_show_error", mock_show_error)

    window._on_save()

    mock_show_error.assert_called_once()
```

### Mocking Locally-Imported Classes

When a class is imported inside a function, mock it at its source module:

```python
# If the code does: from fluxx.gui.simulation import SimulationDialog
# Mock at the source, not the importing module:
monkeypatch.setattr(
    "fluxx.gui.simulation.dialog.SimulationDialog", mock_class
)
```

## Testing Edge Cases

### Missing Versions

Test handling of entities not in the current DAG version:

```python
def test_missing_version() -> None:
    controller = ProjectController()
    task_id = controller.create_task(title="Task", ...)

    project = controller.get_project()
    persistent_id = project.dag.node_map[task_id]
    persistent_task = project.persistent_tasks[persistent_id]

    # Remove from current version
    del persistent_task.versions[project.dag.current_version_id]

    # Test that code handles this gracefully
    result = function_under_test(project)
    assert task_id not in result
```

### Bypassing Validation for Edge Cases

Some tests need invalid states (e.g., cycles) that validation would reject:

```python
def test_cycle_handling() -> None:
    # Create entities normally
    task1_id = controller.create_task(...)
    task2_id = controller.create_task(...)

    # Add dependencies directly to bypass validation
    project = controller.get_project()
    task1 = project.persistent_tasks[...].versions[...]
    task1.dependencies.append(cyclic_dependency)

    # Test that code handles the invalid state gracefully
```

## Common Pitfalls

1. **Forgetting QT_QPA_PLATFORM**: Tests will crash in sandboxed environments without `QT_QPA_PLATFORM=offscreen`

2. **Dialog Hangs**: Unmocked Qt dialogs will hang forever waiting for user input

3. **Fixture Conflicts**: If a fixture mocks something, your test may need a fresh instance:
   ```python
   def test_needs_real_method(qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch) -> None:
       # Create fresh window without fixture's mocking
       win = MainWindow()
       qtbot.addWidget(win)
   ```

4. **Wrong Mock Path**: Mock where the name is looked up, not where it's defined

5. **Type Errors in Tests**: Tests are type-checked too. Use proper types:
   ```python
   # Wrong
   pw = PossibleWorld(id="pw1", title="World", probability=0.5)

   # Correct
   pw = PossibleWorld(id=PossibleWorldId("pw1"), title="World", weight=0.5)
   ```

## Coverage Goals

- Non-GUI modules: 100% coverage required
- GUI modules: >90% coverage target
- Use `make coverage` to identify files with incomplete coverage
