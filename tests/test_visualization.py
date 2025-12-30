"""Tests for visualization components."""

from fluxx.visualization.gantt import GanttChartGenerator


def test_gantt_generator_init() -> None:
    """Test creating a Gantt chart generator."""
    generator = GanttChartGenerator()
    assert generator.percentile == 0.97


def test_gantt_generator_custom_percentile() -> None:
    """Test creating a Gantt chart generator with custom percentile."""
    generator = GanttChartGenerator(percentile=0.90)
    assert generator.percentile == 0.90


def test_gantt_generator_generate() -> None:
    """Test generating a Gantt chart (stub)."""
    generator = GanttChartGenerator()
    # This is a stub, so it should complete without error
    generator.generate()
