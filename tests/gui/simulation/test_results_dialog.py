"""Tests for simulation results dialog."""

from datetime import UTC, datetime

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import NodeId, Sample, SampleId, TaskEvent
from fluxx.gui.simulation.results_dialog import SimulationResultsDialog


@pytest.fixture
def sample_data() -> list[Sample]:
    """Create sample simulation data."""
    samples = []
    for i in range(5):
        events = [
            TaskEvent(
                node_id=NodeId("t1"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1 + i, 17, 0, 0, tzinfo=UTC),
                details={},
            )
        ]
        samples.append(Sample(sample_id=SampleId(i), events=events, failed_tasks=[]))
    return samples


def test_results_dialog_initialization(
    qtbot: QtBot,
    sample_data: list[Sample],
) -> None:
    """Test results dialog initializes correctly."""
    dialog = SimulationResultsDialog(sample_data)
    qtbot.addWidget(dialog)

    # Check dialog properties
    assert dialog.windowTitle() == "Simulation Results"
    assert not dialog.isModal()  # Should be non-modal

    # Should have timeline widget
    assert dialog.timeline_widget is not None


def test_results_dialog_contains_timeline_widget(
    qtbot: QtBot,
    sample_data: list[Sample],
) -> None:
    """Test that results dialog contains timeline widget."""
    dialog = SimulationResultsDialog(sample_data)
    qtbot.addWidget(dialog)

    # Timeline widget should be created with samples
    assert dialog.timeline_widget.samples == sample_data


def test_results_dialog_close_button(
    qtbot: QtBot,
    sample_data: list[Sample],
) -> None:
    """Test that close button works."""
    dialog = SimulationResultsDialog(sample_data)
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
