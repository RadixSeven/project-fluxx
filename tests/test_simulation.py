"""Tests for simulation engine."""

from datetime import UTC, datetime

from fluxx.simulation.engine import SimulationEngine


def test_simulation_engine_init() -> None:
    """Test creating a simulation engine."""
    engine = SimulationEngine(num_samples=100)
    assert engine.num_samples == 100


def test_simulation_engine_with_start_date() -> None:
    """Test creating a simulation engine with a start date."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    engine = SimulationEngine(num_samples=100, start_date=start)
    assert engine.start_date == start


def test_simulation_engine_run() -> None:
    """Test running a simulation (stub)."""
    engine = SimulationEngine(num_samples=10)
    # This is a stub, so it should complete without error
    engine.run()
