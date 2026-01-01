"""Tests for probabilistic timeline widget."""

from datetime import UTC, datetime

import pytest
from pytestqt.qtbot import QtBot

from fluxx.data.models import Sample, SampleId, TaskEvent, TaskId
from fluxx.gui.simulation.timeline_widget import ProbabilisticTimelineWidget


@pytest.fixture
def successful_samples() -> list[Sample]:
    """Create successful samples with varying completion times."""
    samples = []

    for i in range(10):
        events = [
            TaskEvent(
                node_id=TaskId("t1"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1 + i, 17, 0, 0, tzinfo=UTC),
                details={},
            )
        ]
        samples.append(Sample(sample_id=SampleId(i), events=events, failed_tasks=[]))

    return samples


@pytest.fixture
def mixed_samples() -> list[Sample]:
    """Create samples with both successful and failed runs."""
    samples = []

    # 8 successful
    for i in range(8):
        events = [
            TaskEvent(
                node_id=TaskId("t1"),
                event_type="complete",
                timestamp=datetime(2024, 1, 1 + i, 17, 0, 0, tzinfo=UTC),
                details={},
            )
        ]
        samples.append(Sample(sample_id=SampleId(i), events=events, failed_tasks=[]))

    # 2 failed
    for i in range(8, 10):
        events = [
            TaskEvent(
                node_id=TaskId("t1"),
                event_type="start",
                timestamp=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
                details={},
            )
        ]
        samples.append(
            Sample(sample_id=SampleId(i), events=events, failed_tasks=[TaskId("t2")])
        )

    return samples


def test_timeline_widget_initialization(
    qtbot: QtBot,
    successful_samples: list[Sample],
) -> None:
    """Test widget initializes with successful samples."""
    widget = ProbabilisticTimelineWidget(successful_samples)
    qtbot.addWidget(widget)

    # Widget should have extracted completion times
    assert len(widget.completion_times) == 10

    # Stats label should be populated
    assert widget.stats_label.text() != ""
    assert "Success Rate: 100.0%" in widget.stats_label.text()
    assert "P50 (Median):" in widget.stats_label.text()


def test_timeline_widget_with_mixed_results(
    qtbot: QtBot,
    mixed_samples: list[Sample],
) -> None:
    """Test widget with both successful and failed samples."""
    widget = ProbabilisticTimelineWidget(mixed_samples)
    qtbot.addWidget(widget)

    # Should only extract successful completion times
    assert len(widget.completion_times) == 8

    # Success rate should be 80%
    assert "Success Rate: 80.0%" in widget.stats_label.text()


def test_timeline_widget_with_no_successful_samples(qtbot: QtBot) -> None:
    """Test widget with all failed samples."""
    failed_sample = Sample(
        sample_id=SampleId(0),
        events=[],
        failed_tasks=[TaskId("t1")],
    )

    widget = ProbabilisticTimelineWidget([failed_sample])
    qtbot.addWidget(widget)

    # Should have no completion times
    assert len(widget.completion_times) == 0

    # Stats label should show message
    assert "No successful samples" in widget.stats_label.text()


def test_timeline_widget_histogram_updates(
    qtbot: QtBot,
    successful_samples: list[Sample],
) -> None:
    """Test that histogram is updated."""
    widget = ProbabilisticTimelineWidget(successful_samples)
    qtbot.addWidget(widget)

    # Chart should have title
    assert widget.ax.get_title() == "Project Completion Date Distribution"

    # Should have xlabel and ylabel
    assert widget.ax.get_xlabel() != ""
    assert widget.ax.get_ylabel() != ""

    # Should have percentile lines in legend
    legend = widget.ax.get_legend()
    assert legend is not None


def test_timeline_widget_creates_canvas(
    qtbot: QtBot,
    successful_samples: list[Sample],
) -> None:
    """Test that matplotlib canvas is created."""
    widget = ProbabilisticTimelineWidget(successful_samples)
    qtbot.addWidget(widget)

    # Canvas should exist
    assert widget.canvas is not None
    assert widget.figure is not None
    assert widget.ax is not None
