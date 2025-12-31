"""Tests for simulation dialog."""

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QDate
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    NodeId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Triangular,
)
from fluxx.gui.simulation.dialog import SimulationDialog


@pytest.fixture
def simple_project() -> Project:
    """Create a simple project for testing."""
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
        node_map={NodeId("t1"): PersistentObjectId("pt1")},
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
    )


def test_dialog_initialization(qtbot: QtBot, simple_project: Project) -> None:
    """Test dialog initializes with default values."""
    dialog = SimulationDialog(simple_project)
    qtbot.addWidget(dialog)

    # Check default values
    assert dialog.num_samples_spin.value() == 1000
    assert dialog.num_workers_spin.value() == 2
    assert dialog.hours_per_day_spin.value() == 8

    # Check date is today
    today = datetime.now(UTC).date()
    dialog_date = dialog.start_date_edit.date()
    assert dialog_date.year() == today.year
    assert dialog_date.month() == today.month
    assert dialog_date.day() == today.day

    # Check widgets are enabled
    assert dialog.num_samples_spin.isEnabled()
    assert dialog.start_date_edit.isEnabled()
    assert dialog.num_workers_spin.isEnabled()
    assert dialog.hours_per_day_spin.isEnabled()

    # Check progress widgets are hidden
    assert not dialog.progress_label.isVisible()
    assert not dialog.progress_bar.isVisible()


def test_dialog_modifies_parameters(qtbot: QtBot, simple_project: Project) -> None:
    """Test modifying dialog parameters."""
    dialog = SimulationDialog(simple_project)
    qtbot.addWidget(dialog)

    # Modify values
    dialog.num_samples_spin.setValue(500)
    dialog.num_workers_spin.setValue(5)
    dialog.hours_per_day_spin.setValue(6)
    dialog.start_date_edit.setDate(QDate(2025, 6, 15))

    # Verify changes
    assert dialog.num_samples_spin.value() == 500
    assert dialog.num_workers_spin.value() == 5
    assert dialog.hours_per_day_spin.value() == 6

    date = dialog.start_date_edit.date()
    assert date.year() == 2025
    assert date.month() == 6
    assert date.day() == 15


def test_dialog_create_workers(simple_project: Project) -> None:
    """Test worker creation method."""
    dialog = SimulationDialog(simple_project)

    workers = dialog._create_workers(3, 7.5)

    assert len(workers) == 3
    assert all(w.hours_per_workday == 7.5 for w in workers)
    assert workers[0].name == "Worker 1"
    assert workers[1].name == "Worker 2"
    assert workers[2].name == "Worker 3"


def test_dialog_set_inputs_enabled(simple_project: Project) -> None:
    """Test enabling/disabling input widgets."""
    dialog = SimulationDialog(simple_project)

    # Disable inputs
    dialog._set_inputs_enabled(False)

    assert not dialog.num_samples_spin.isEnabled()
    assert not dialog.start_date_edit.isEnabled()
    assert not dialog.num_workers_spin.isEnabled()
    assert not dialog.hours_per_day_spin.isEnabled()
    assert not dialog.run_button.isEnabled()

    # Re-enable inputs
    dialog._set_inputs_enabled(True)

    assert dialog.num_samples_spin.isEnabled()
    assert dialog.start_date_edit.isEnabled()
    assert dialog.num_workers_spin.isEnabled()
    assert dialog.hours_per_day_spin.isEnabled()
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
    samples_emitted: list[object] = []

    def on_completed(samples: list[object]) -> None:
        samples_emitted.append(samples)

    dialog.simulation_completed.connect(on_completed)

    # Trigger simulation (simulates clicking Run button)
    with qtbot.waitSignal(dialog.simulation_completed, timeout=10000):
        dialog._on_run()

    # Verify simulation completed
    from typing import cast

    from fluxx.data.models import Sample

    assert len(samples_emitted) == 1
    samples = cast(list[Sample], samples_emitted[0])
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
