"""Tests for simulation dialog."""

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QDate
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.gui.simulation.dialog import SimulationDialog


@pytest.fixture
def simple_project() -> Project:
    """Create a simple project for testing with workers."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    workers = [
        Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0),
        Worker(id=WorkerId("w2"), name="Bob", hours_per_workday=8.0),
    ]

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=workers,
    )


@pytest.fixture
def project_without_workers() -> Project:
    """Create a project with no workers for testing."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=[],
    )


def test_dialog_initialization(qtbot: QtBot, simple_project: Project) -> None:
    """Test dialog initializes with default values."""
    dialog = SimulationDialog(simple_project)
    qtbot.addWidget(dialog)

    # Check default values
    assert dialog.num_samples_spin.value() == 1000

    # Check date is today
    today = datetime.now(UTC).date()
    dialog_date = dialog.start_date_edit.date()
    assert dialog_date.year() == today.year
    assert dialog_date.month() == today.month
    assert dialog_date.day() == today.day

    # Check widgets are enabled (project has workers)
    assert dialog.num_samples_spin.isEnabled()
    assert dialog.start_date_edit.isEnabled()
    assert dialog.run_button.isEnabled()

    # Check workers are displayed
    assert "2 workers" in dialog.workers_label.text()
    assert "Alice" in dialog.workers_label.text()

    # Check progress widgets are hidden
    assert not dialog.progress_label.isVisible()
    assert not dialog.progress_bar.isVisible()


def test_dialog_modifies_parameters(qtbot: QtBot, simple_project: Project) -> None:
    """Test modifying dialog parameters."""
    dialog = SimulationDialog(simple_project)
    qtbot.addWidget(dialog)

    # Modify values
    dialog.num_samples_spin.setValue(500)
    dialog.start_date_edit.setDate(QDate(2025, 6, 15))

    # Verify changes
    assert dialog.num_samples_spin.value() == 500

    date = dialog.start_date_edit.date()
    assert date.year() == 2025
    assert date.month() == 6
    assert date.day() == 15


def test_dialog_no_workers_disables_run(
    qtbot: QtBot, project_without_workers: Project
) -> None:
    """Test that Run button is disabled when no workers."""
    dialog = SimulationDialog(project_without_workers)
    qtbot.addWidget(dialog)

    # Run button should be disabled
    assert not dialog.run_button.isEnabled()

    # Should have tooltip explaining why
    assert "Add workers" in dialog.run_button.toolTip()

    # Workers label should indicate no workers
    assert "No workers" in dialog.workers_label.text()


def test_dialog_set_inputs_enabled(simple_project: Project) -> None:
    """Test enabling/disabling input widgets."""
    dialog = SimulationDialog(simple_project)

    # Disable inputs
    dialog._set_inputs_enabled(False)

    assert not dialog.num_samples_spin.isEnabled()
    assert not dialog.start_date_edit.isEnabled()
    assert not dialog.run_button.isEnabled()

    # Re-enable inputs
    dialog._set_inputs_enabled(True)

    assert dialog.num_samples_spin.isEnabled()
    assert dialog.start_date_edit.isEnabled()
    assert dialog.run_button.isEnabled()


def test_dialog_run_simulation_small_sample(
    qtbot: QtBot,
    simple_project: Project,
) -> None:
    """Test running a small simulation."""
    dialog = SimulationDialog(simple_project)
    qtbot.addWidget(dialog)

    # Set small sample size for fast test
    dialog.num_samples_spin.setValue(2)

    # Track signal emissions
    from fluxx.data.models import Sample

    samples_emitted: list[list[Sample]] = []

    def on_completed(sample_list: list[Sample]) -> None:
        samples_emitted.append(sample_list)

    dialog.simulation_completed.connect(on_completed)

    # Trigger simulation (simulates clicking Run button)
    with qtbot.waitSignal(dialog.simulation_completed, timeout=10000):
        dialog._on_run()

    # Verify simulation completed

    assert len(samples_emitted) == 1
    samples = samples_emitted[0]
    assert len(samples) == 2

    # All samples should be successful for this simple project
    for sample in samples:
        assert len(sample.failed_tasks) == 0
        assert len(sample.events) > 0


def test_dialog_reject_closes_dialog(qtbot: QtBot, simple_project: Project) -> None:
    """Test that Cancel button closes dialog."""
    dialog = SimulationDialog(simple_project)
    qtbot.addWidget(dialog)

    # Click Cancel button
    cancel_button = dialog.button_box.button(dialog.button_box.StandardButton.Cancel)
    assert cancel_button is not None

    with qtbot.waitSignal(dialog.rejected):
        cancel_button.click()


def test_dialog_single_worker(qtbot: QtBot) -> None:
    """Test dialog with exactly one worker shows correct text."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    # Only one worker
    workers = [Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0)]

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=workers,
    )

    dialog = SimulationDialog(project)
    qtbot.addWidget(dialog)

    # Check single worker text format
    assert "1 worker" in dialog.workers_label.text()
    assert "Alice" in dialog.workers_label.text()


def test_dialog_many_workers(qtbot: QtBot) -> None:
    """Test dialog with more than 3 workers shows truncated list."""
    task = Task(
        id=TaskId("t1"),
        title="Task 1",
        description="Test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    version_id = DAGVersionId("v1")
    persistent_task = PersistentTask(
        id=PersistentObjectId("pt1"),
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={TaskId("t1"): PersistentObjectId("pt1")},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )

    # More than 3 workers
    workers = [
        Worker(id=WorkerId("w1"), name="Alice", hours_per_workday=8.0),
        Worker(id=WorkerId("w2"), name="Bob", hours_per_workday=8.0),
        Worker(id=WorkerId("w3"), name="Carol", hours_per_workday=8.0),
        Worker(id=WorkerId("w4"), name="Dave", hours_per_workday=8.0),
        Worker(id=WorkerId("w5"), name="Eve", hours_per_workday=8.0),
    ]

    project = Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={PersistentObjectId("pt1"): persistent_task},
        workers=workers,
    )

    dialog = SimulationDialog(project)
    qtbot.addWidget(dialog)

    # Check many workers text format with truncation
    assert "5 workers" in dialog.workers_label.text()
    assert "(+2 more)" in dialog.workers_label.text()


def test_dialog_set_inputs_enabled_no_workers(
    project_without_workers: Project,
) -> None:
    """Test enabling inputs keeps Run disabled when no workers."""
    dialog = SimulationDialog(project_without_workers)

    # Run button should start disabled
    assert not dialog.run_button.isEnabled()

    # Disable and re-enable inputs
    dialog._set_inputs_enabled(False)
    dialog._set_inputs_enabled(True)

    # Run button should still be disabled (no workers)
    assert not dialog.run_button.isEnabled()
