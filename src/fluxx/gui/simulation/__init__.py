"""GUI components for running and visualizing simulations."""

from fluxx.gui.simulation.analysis import (
    calculate_percentiles,
    calculate_statistics,
    calculate_success_rate,
    extract_completion_times,
    prepare_histogram_data,
)
from fluxx.gui.simulation.dialog import SimulationDialog
from fluxx.gui.simulation.results_dialog import SimulationResultsDialog
from fluxx.gui.simulation.timeline_widget import ProbabilisticTimelineWidget

__all__ = [
    "SimulationDialog",
    "SimulationResultsDialog",
    "ProbabilisticTimelineWidget",
    "extract_completion_times",
    "calculate_percentiles",
    "calculate_success_rate",
    "calculate_statistics",
    "prepare_histogram_data",
]
