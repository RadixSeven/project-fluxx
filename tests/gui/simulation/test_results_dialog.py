"""Tests for simulation results dialog."""

from datetime import UTC, datetime

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Sample,
    SampleId,
    Task,
    TaskEvent,
    TaskId,
    Triangular,
)
from fluxx.gui.simulation.results_dialog import SimulationResultsDialog


@pytest.fixture
def simple_project() -> Project:
    """Create a simple project for testing."""
    version_id = DAGVersionId("v1")

    # Create a simple task
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
    )

    # Create persistent task
    persistent_tasks = {
        PersistentObjectId("pt1"): PersistentTask(
            id=PersistentObjectId("pt1"),
            versions={version_id: task},
        ),
    }

    # Create DAG
    dag = DAG(
        id=DAGId("dag1"),
        current_version_id=version_id,
        node_map={
            TaskId("t1"): PersistentObjectId("pt1"),
        },
    )

    # Create project
    project = Project(
        metadata=ProjectMetadata(
            name="Test Project",
            created=datetime.now(UTC),
            last_modified=datetime.now(UTC),
        ),
        dag=dag,
        persistent_tasks=persistent_tasks,
    )

    return project


@pytest.fixture
def sample_data() -> list[Sample]:
    """Create sample simulation data."""
    samples = []
    for i in range(5):
        events = [
            TaskEvent(
                node_id=TaskId("t1"),
                event_type="start",
                timestamp=datetime(2024, 1, 1 + i, 9, 0, 0, tzinfo=UTC),
                details={},
            ),
            TaskEvent(
                node_id=TaskId("t1"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1 + i, 17, 0, 0, tzinfo=UTC),
                details={},
            ),
        ]
        samples.append(Sample(sample_id=SampleId(i), events=events, failed_tasks=[]))
    return samples


def test_results_dialog_initialization(
    qtbot: QtBot,
    sample_data: list[Sample],
    simple_project: Project,
) -> None:
    """Test results dialog initializes correctly."""
    dialog = SimulationResultsDialog(sample_data, simple_project)
    qtbot.addWidget(dialog)

    # Check dialog properties
    assert dialog.windowTitle() == "Simulation Results"
    assert not dialog.isModal()  # Should be non-modal

    # Should have timeline widget
    assert dialog.timeline_widget is not None
    assert dialog.histogram_widget is not None
    assert dialog.tabs is not None


def test_results_dialog_contains_both_views(
    qtbot: QtBot,
    sample_data: list[Sample],
    simple_project: Project,
) -> None:
    """Test that results dialog contains all three views."""
    dialog = SimulationResultsDialog(sample_data, simple_project)
    qtbot.addWidget(dialog)

    # Should have three tabs
    assert dialog.tabs.count() == 3

    # Check tab names
    assert dialog.tabs.tabText(0) == "Probabilistic Timeline"
    assert dialog.tabs.tabText(1) == "Conservative Gantt Chart"
    assert dialog.tabs.tabText(2) == "Completion Date Distribution"


def test_results_dialog_timeline_widget_created(
    qtbot: QtBot,
    sample_data: list[Sample],
    simple_project: Project,
) -> None:
    """Test that probabilistic timeline widget is created with timeline data."""
    dialog = SimulationResultsDialog(sample_data, simple_project, percentile=95.0)
    qtbot.addWidget(dialog)

    # Timeline widget should be created
    assert dialog.timeline_widget is not None
    assert dialog.timeline_widget.timeline_data is not None
    assert dialog.timeline_widget.timeline_data.percentile == 95.0


def test_results_dialog_close_button(
    qtbot: QtBot,
    sample_data: list[Sample],
    simple_project: Project,
) -> None:
    """Test that close button works."""
    dialog = SimulationResultsDialog(sample_data, simple_project)
    qtbot.addWidget(dialog)

    # Get close button
    close_button = dialog.button_box.button(dialog.button_box.StandardButton.Close)
    assert close_button is not None

    # Show dialog first
    dialog.show()
    assert dialog.isVisible()

    # Click should close dialog
    close_button.click()
    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=1000)
