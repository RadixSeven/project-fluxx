"""Tests for data models."""

import pytest

from fluxx.data.models import ShiftedLognormal, Triangular, Worker


def test_worker_creation() -> None:
    """Test creating a worker."""
    worker = Worker(id="w1", name="Alice", worker_id="alice_1", hours_per_workday=8.0)
    assert worker.name == "Alice"
    assert worker.hours_per_workday == 8.0


def test_worker_optional_id() -> None:
    """Test that worker_id is optional."""
    worker = Worker(id="w1", name="Bob", hours_per_workday=6.0)
    assert worker.worker_id is None


def test_shifted_lognormal_valid() -> None:
    """Test creating a valid shifted lognormal distribution."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=10.0)
    assert dist.min == 1.0
    assert dist.mode == 5.0
    assert dist.percentile_95 == 10.0


def test_shifted_lognormal_mode_validation() -> None:
    """Test that mode must be > min."""
    with pytest.raises(ValueError, match="mode must be greater than min"):
        ShiftedLognormal(min=5.0, mode=3.0, percentile_95=10.0)


def test_shifted_lognormal_percentile_validation() -> None:
    """Test that percentile_95 must be > min."""
    with pytest.raises(ValueError, match="percentile_95 must be greater than min"):
        ShiftedLognormal(min=10.0, mode=15.0, percentile_95=8.0)


def test_triangular_valid() -> None:
    """Test creating a valid triangular distribution."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    assert dist.min == 1.0
    assert dist.mode == 5.0
    assert dist.max == 10.0


def test_triangular_mode_validation() -> None:
    """Test that mode must be > min."""
    with pytest.raises(ValueError, match="mode must be greater than min"):
        Triangular(min=5.0, mode=3.0, max=10.0)


def test_triangular_max_validation() -> None:
    """Test that max must be > mode."""
    with pytest.raises(ValueError, match="max must be greater than mode"):
        Triangular(min=1.0, mode=8.0, max=7.0)
