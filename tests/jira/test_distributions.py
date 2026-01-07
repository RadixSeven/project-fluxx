"""Tests for Jira empirical distribution binning."""

import numpy as np
import pytest

from fluxx.jira.distributions import (
    EmpiricalEstimateBin,
    InsufficientDataError,
    create_empirical_bins,
    find_empirical_bin_for_estimate,
)


class TestEmpiricalEstimateBin:
    """Tests for EmpiricalEstimateBin dataclass."""

    def test_sample_returns_actual_duration(self) -> None:
        """Sample should return an actual duration from the bin."""
        bin_ = EmpiricalEstimateBin(
            center_estimate=5.0,
            lower_bound=3.0,
            upper_bound=7.0,
            samples=[(4.0, 10.0), (5.0, 12.0), (6.0, 8.0)],
        )
        rng = np.random.default_rng(42)
        sample = bin_.sample(rng)
        # Sample should be one of the actual durations
        assert sample in [10.0, 12.0, 8.0]

    def test_sample_distribution(self) -> None:
        """Sampling should follow the multiset distribution."""
        # Create a bin with known distribution: 40% 10, 40% 8, 20% 11
        bin_ = EmpiricalEstimateBin(
            center_estimate=8.0,
            lower_bound=0.0,
            upper_bound=float("inf"),
            samples=[
                (8.0, 10.0),
                (8.0, 10.0),
                (8.0, 11.0),
                (9.0, 8.0),
                (10.0, 8.0),
            ],
        )
        rng = np.random.default_rng(42)
        counts: dict[float, int] = {8.0: 0, 10.0: 0, 11.0: 0}
        for _ in range(10000):
            sample = bin_.sample(rng)
            counts[sample] += 1

        # Check proportions are roughly correct (within 5%)
        total = sum(counts.values())
        assert abs(counts[10.0] / total - 0.4) < 0.05  # 40% for 10
        assert abs(counts[8.0] / total - 0.4) < 0.05  # 40% for 8
        assert abs(counts[11.0] / total - 0.2) < 0.05  # 20% for 11

    def test_sample_filtered_returns_valid_sample(self) -> None:
        """sample_filtered should return samples above threshold."""
        bin_ = EmpiricalEstimateBin(
            center_estimate=5.0,
            lower_bound=0.0,
            upper_bound=float("inf"),
            samples=[(4.0, 5.0), (5.0, 10.0), (6.0, 15.0)],
        )
        rng = np.random.default_rng(42)
        sample = bin_.sample_filtered(rng, min_duration=8.0)
        # Only 10.0 and 15.0 are > 8.0
        assert sample in [10.0, 15.0]

    def test_sample_filtered_returns_none_when_no_valid_samples(self) -> None:
        """sample_filtered returns None when no samples exceed threshold."""
        bin_ = EmpiricalEstimateBin(
            center_estimate=5.0,
            lower_bound=0.0,
            upper_bound=float("inf"),
            samples=[(4.0, 5.0), (5.0, 6.0), (6.0, 7.0)],
        )
        rng = np.random.default_rng(42)
        sample = bin_.sample_filtered(rng, min_duration=10.0)
        assert sample is None


class TestCreateEmpiricalBins:
    """Tests for create_empirical_bins function."""

    def test_create_bins_minimum_samples(self) -> None:
        """Each bin should have at least min_samples entries."""
        data = [(float(i), float(i * 2)) for i in range(1, 101)]
        bins = create_empirical_bins(data, min_samples=10)
        for bin_ in bins:
            assert len(bin_.samples) >= 10

    def test_create_bins_single_bin_when_few_samples(self) -> None:
        """When total samples < min_samples, create one bin."""
        data = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]
        bins = create_empirical_bins(data, min_samples=30)
        assert len(bins) == 1
        # Should contain all the (estimate, actual) pairs
        assert len(bins[0].samples) == 3
        assert bins[0].samples == [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]

    def test_create_bins_stores_estimate_actual_pairs(self) -> None:
        """Bins should store (estimate, actual) pairs, not just actuals."""
        data = [(4.0, 10.0), (5.0, 12.0), (6.0, 8.0)]
        bins = create_empirical_bins(data, min_samples=2)
        # Check that samples are tuples, not just floats
        for bin_ in bins:
            for sample in bin_.samples:
                assert isinstance(sample, tuple)
                assert len(sample) == 2

    def test_lowest_bin_has_zero_lower_bound(self) -> None:
        """The lowest bin should have lower_bound=0."""
        data = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0)]
        bins = create_empirical_bins(data, min_samples=3)
        lowest_bin = min(bins, key=lambda b: b.center_estimate)
        assert lowest_bin.lower_bound == 0.0

    def test_highest_bin_has_inf_upper_bound(self) -> None:
        """The highest bin should have upper_bound=inf."""
        data = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0)]
        bins = create_empirical_bins(data, min_samples=3)
        highest_bin = max(bins, key=lambda b: b.center_estimate)
        assert highest_bin.upper_bound == float("inf")

    def test_create_bins_empty_data(self) -> None:
        """Empty data list returns empty bins list."""
        bins = create_empirical_bins([], min_samples=30)
        assert bins == []

    def test_create_bins_deduplicates_identical_sample_sets(self) -> None:
        """Bins with identical sample sets should be deduplicated."""
        # Create data where multiple centers result in same samples
        data = [
            (1.0, 2.0),
            (1.0, 3.0),
            (1.0, 4.0),
            (2.0, 3.0),
            (2.0, 4.0),
            (2.0, 5.0),
        ]
        bins = create_empirical_bins(data, min_samples=3)
        # Check that we don't have duplicate bins
        sample_sets = [tuple(sorted(b.samples)) for b in bins]
        assert len(sample_sets) == len(set(sample_sets))


class TestFindEmpiricalBinForEstimate:
    """Tests for find_empirical_bin_for_estimate function."""

    def test_find_bin_within_bounds(self) -> None:
        """Find the right bin when estimate is within bounds."""
        bins = [
            EmpiricalEstimateBin(
                center_estimate=5.0,
                lower_bound=0.0,
                upper_bound=7.5,
                samples=[(4.0, 10.0), (5.0, 12.0), (6.0, 8.0)],
            ),
            EmpiricalEstimateBin(
                center_estimate=10.0,
                lower_bound=7.5,
                upper_bound=float("inf"),
                samples=[(9.0, 15.0), (10.0, 18.0), (11.0, 14.0)],
            ),
        ]

        # Estimate of 6 should be in first bin
        bin_found = find_empirical_bin_for_estimate(6.0, bins)
        assert bin_found.center_estimate == 5.0

        # Estimate of 12 should be in second bin
        bin_found = find_empirical_bin_for_estimate(12.0, bins)
        assert bin_found.center_estimate == 10.0

    def test_find_bin_at_zero_lower_bound(self) -> None:
        """Find bin when estimate is at zero and bin has lower_bound=0."""
        bins = [
            EmpiricalEstimateBin(
                center_estimate=5.0,
                lower_bound=0.0,
                upper_bound=10.0,
                samples=[(4.0, 10.0), (5.0, 12.0), (6.0, 8.0)],
            ),
        ]

        bin_found = find_empirical_bin_for_estimate(0.0, bins)
        assert bin_found.center_estimate == 5.0

    def test_find_bin_outside_bounds_returns_closest(self) -> None:
        """Find closest bin when estimate is outside all bounds."""
        bins = [
            EmpiricalEstimateBin(
                center_estimate=5.0,
                lower_bound=2.0,
                upper_bound=8.0,
                samples=[(4.0, 10.0), (5.0, 12.0), (6.0, 8.0)],
            ),
            EmpiricalEstimateBin(
                center_estimate=15.0,
                lower_bound=10.0,
                upper_bound=20.0,
                samples=[(14.0, 20.0), (15.0, 22.0), (16.0, 18.0)],
            ),
        ]

        # Estimate of 1 is outside all bounds, closest center is 5.0
        bin_found = find_empirical_bin_for_estimate(1.0, bins)
        assert bin_found.center_estimate == 5.0

        # Estimate of 9 is between bins, closer to 5 (dist 4) than 15 (dist 6)
        bin_found = find_empirical_bin_for_estimate(9.0, bins)
        assert bin_found.center_estimate == 5.0

    def test_find_bin_equidistant_prefers_higher(self) -> None:
        """When equidistant from two bins, prefer the higher estimate bin."""
        bins = [
            EmpiricalEstimateBin(
                center_estimate=5.0,
                lower_bound=2.0,
                upper_bound=8.0,
                samples=[(4.0, 10.0), (5.0, 12.0), (6.0, 8.0)],
            ),
            EmpiricalEstimateBin(
                center_estimate=15.0,
                lower_bound=10.0,
                upper_bound=20.0,
                samples=[(14.0, 20.0), (15.0, 22.0), (16.0, 18.0)],
            ),
        ]

        # Estimate of 10 is equidistant from 5 and 15
        bin_found = find_empirical_bin_for_estimate(10.0, bins)
        # Should prefer higher center (15.0) - conservative approach
        assert bin_found.center_estimate == 15.0


class TestInsufficientDataError:
    """Tests for InsufficientDataError exception."""

    def test_exception_can_be_raised(self) -> None:
        """InsufficientDataError can be raised and caught."""
        with pytest.raises(InsufficientDataError):
            raise InsufficientDataError("Not enough data")
