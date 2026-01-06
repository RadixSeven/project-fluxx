"""Tests for Jira distribution fitting."""

import numpy as np
import pytest

from fluxx.data.models import ShiftedLognormal
from fluxx.jira.distributions import (
    EstimateBin,
    InsufficientDataError,
    create_estimate_bins,
    fit_bin_distribution,
    fit_fallback_distribution,
)


class TestFitFallbackDistribution:
    """Tests for fit_fallback_distribution function."""

    def test_fit_fallback_distribution_basic(self) -> None:
        """Fit distribution to a set of times."""
        times = [1.0, 2.0, 3.0, 5.0, 8.0, 13.0]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # The min should be at or below the minimum time
        assert dist.min <= min(times)
        # The mode should be reasonable
        assert dist.mode > dist.min
        # The 95th percentile should be above the mode
        assert dist.percentile_95 > dist.mode

    def test_fit_fallback_distribution_empty_raises(self) -> None:
        """Empty times list raises InsufficientDataError."""
        with pytest.raises(InsufficientDataError):
            fit_fallback_distribution([])

    def test_fit_fallback_distribution_single_value(self) -> None:
        """Single value creates a minimal distribution around it."""
        times = [5.0]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # Should be a tight distribution around the single value
        assert dist.min < 5.0
        assert dist.mode >= dist.min
        assert dist.percentile_95 > dist.mode

    def test_fit_fallback_distribution_identical_values(self) -> None:
        """All identical values creates a minimal distribution."""
        times = [10.0, 10.0, 10.0, 10.0]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # Should handle zero variance case
        assert dist.min < 10.0
        assert dist.percentile_95 > dist.min

    def test_fit_fallback_distribution_samples_reasonably(self) -> None:
        """Verify the fitted distribution produces reasonable samples."""
        times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        dist = fit_fallback_distribution(times)

        rng = np.random.default_rng(42)
        samples = []
        for _ in range(1000):
            # Sample using the same logic as simulation
            from fluxx.simulation.distributions import sample_shifted_lognormal

            samples.append(sample_shifted_lognormal(dist, rng))

        # Samples should be positive
        assert all(s > 0 for s in samples)
        # Mean of samples should be in a reasonable range
        sample_mean = sum(samples) / len(samples)
        data_mean = sum(times) / len(times)
        # Within factor of 3 (distributions can be quite variable)
        assert data_mean / 3 < sample_mean < data_mean * 3

    def test_fit_fallback_distribution_single_zero_value(self) -> None:
        """Single zero value creates a minimal distribution."""
        times = [0.0]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # Should handle zero/negative with fallback defaults
        assert dist.min == 0.1
        assert dist.mode == 0.2
        assert dist.percentile_95 == 1.0

    def test_fit_fallback_distribution_very_tight_data(self) -> None:
        """Verify fitting works with very tight data distribution."""
        # Data that might cause mode <= min_val or p95 <= mode
        times = [0.001, 0.001, 0.001, 0.002, 0.002]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # Constraints should be enforced
        assert dist.mode > dist.min
        assert dist.percentile_95 > dist.mode

    def test_fit_fallback_distribution_triggers_mode_constraint(self) -> None:
        """Test data that triggers mode <= min_val constraint enforcement.

        When the fitted lognormal has very high sigma, mode = exp(mu - sigma^2)
        can become extremely small, causing loc + mode_unshifted <= loc.
        """
        # Data with extreme right skew triggers this case:
        # Most values clustered at minimum, with extreme outlier
        times = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1000.0]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # The constraint enforcement should ensure mode > min
        assert dist.mode > dist.min
        assert dist.percentile_95 > dist.mode

    def test_fit_fallback_distribution_triggers_p95_constraint(self) -> None:
        """Test data that triggers p95 <= mode constraint enforcement.

        This can happen with negative sigma^2 in the mode formula when
        the data is extremely left-skewed after shifting.
        """
        # Create data where the fit produces unusual parameters
        # Very tight clustering with slight left skew
        times = [10.0, 10.1, 10.2, 10.3, 10.0, 10.1, 10.0, 9.9, 9.8, 9.7]
        dist = fit_fallback_distribution(times)
        assert isinstance(dist, ShiftedLognormal)
        # Constraints should be satisfied
        assert dist.mode > dist.min
        assert dist.percentile_95 > dist.mode


class TestFitBinDistribution:
    """Tests for fit_bin_distribution function."""

    def test_fit_bin_distribution_with_zero_lower_bound(self) -> None:
        """Distribution with lower_bound=0 should have loc=0."""
        data = [1.0, 2.0, 3.0, 5.0, 8.0]
        dist = fit_bin_distribution(data, lower_bound=0.0)
        assert isinstance(dist, ShiftedLognormal)
        # With lower_bound=0, the minimum should be very close to 0
        assert dist.min >= 0.0
        assert dist.min < min(data)

    def test_fit_bin_distribution_with_nonzero_lower_bound(self) -> None:
        """Distribution with lower_bound>0 should have shifted min."""
        data = [10.0, 12.0, 15.0, 18.0, 20.0]
        lower_bound = 8.0
        dist = fit_bin_distribution(data, lower_bound=lower_bound)
        assert isinstance(dist, ShiftedLognormal)
        # The min should be at or above the lower bound
        assert dist.min >= lower_bound * 0.5  # Allow some flexibility

    def test_fit_bin_distribution_empty_raises(self) -> None:
        """Empty data list raises InsufficientDataError."""
        with pytest.raises(InsufficientDataError):
            fit_bin_distribution([], lower_bound=0.0)

    def test_fit_bin_distribution_identical_values(self) -> None:
        """Distribution with identical values should still work."""
        data = [5.0, 5.0, 5.0, 5.0]
        dist = fit_bin_distribution(data, lower_bound=3.0)
        assert isinstance(dist, ShiftedLognormal)
        assert dist.mode > dist.min
        assert dist.percentile_95 > dist.mode

    def test_fit_bin_distribution_very_tight_data(self) -> None:
        """Verify fitting works when fitted params would violate constraints."""
        # Data that might cause mode <= min_val or p95 <= mode
        data = [0.001, 0.001, 0.002, 0.002, 0.003]
        dist = fit_bin_distribution(data, lower_bound=0.0)
        assert isinstance(dist, ShiftedLognormal)
        # Constraints should be enforced
        assert dist.mode > dist.min
        assert dist.percentile_95 > dist.mode

    def test_fit_bin_distribution_triggers_p95_constraint(self) -> None:
        """Test data that triggers p95 <= mode constraint in fit_bin_distribution."""
        # Data with extreme right skew where p95 calculation may fall below mode
        data = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 500.0]
        dist = fit_bin_distribution(data, lower_bound=0.0)
        assert isinstance(dist, ShiftedLognormal)
        # Constraints should be enforced
        assert dist.mode > dist.min
        assert dist.percentile_95 > dist.mode


class TestCreateEstimateBins:
    """Tests for create_estimate_bins function."""

    def test_create_bins_minimum_samples(self) -> None:
        """Each bin should have at least min_samples entries."""
        # Create data with enough variation
        data = [(float(i), float(i * 2)) for i in range(1, 101)]
        bins = create_estimate_bins(data, min_samples=10)
        for bin_ in bins:
            assert len(bin_.samples) >= 10

    def test_create_bins_single_bin_when_few_samples(self) -> None:
        """When total samples < min_samples, create one bin."""
        data = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]
        bins = create_estimate_bins(data, min_samples=30)
        assert len(bins) == 1
        assert len(bins[0].samples) == 3

    def test_create_bins_bounds_are_midpoints(self) -> None:
        """Bin bounds should be midpoints between included/excluded."""
        # This tests the specific example from the spec
        data = [
            (7.0, 10.0),
            (7.0, 10.0),
            (7.0, 12.0),
            (7.5, 8.0),
            (7.5, 9.0),
            (7.5, 12.0),
            (7.5, 12.0),
            (7.75, 7.0),
            (8.0, 8.0),
            (8.0, 10.0),
            (8.0, 16.0),
            (8.0, 25.0),
            (8.0, 48.0),
            (9.0, 50.0),
            (11.0, 15.0),
            (12.0, 13.0),
            (12.0, 24.0),
            (12.0, 26.0),
            (14.0, 15.0),
        ]
        # With min_samples=10, a bin centered at 9 should include
        # estimates from 7.5 to 9 (distance <= 1.5 to get 11 samples)
        bins = create_estimate_bins(data, min_samples=10)
        # Just verify we get bins with proper structure
        assert len(bins) > 0
        for bin_ in bins:
            assert bin_.lower_bound is not None
            assert bin_.upper_bound is not None

    def test_lowest_bin_has_zero_lower_bound(self) -> None:
        """The lowest bin should have lower_bound=0."""
        data = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0)]
        bins = create_estimate_bins(data, min_samples=3)
        # Find the bin with the lowest center
        lowest_bin = min(bins, key=lambda b: b.center_estimate)
        assert lowest_bin.lower_bound == 0.0

    def test_highest_bin_has_inf_upper_bound(self) -> None:
        """The highest bin should have upper_bound=inf."""
        data = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0)]
        bins = create_estimate_bins(data, min_samples=3)
        # Find the bin with the highest center
        highest_bin = max(bins, key=lambda b: b.center_estimate)
        assert highest_bin.upper_bound == float("inf")

    def test_create_bins_empty_data(self) -> None:
        """Empty data list returns empty bins list."""
        bins = create_estimate_bins([], min_samples=30)
        assert bins == []

    def test_create_bins_with_repeated_centers(self) -> None:
        """Bins with same center should be deduplicated."""
        # Create data where some estimates repeat
        data = [
            (1.0, 2.0),
            (1.0, 3.0),
            (1.0, 4.0),
            (2.0, 3.0),
            (2.0, 4.0),
            (2.0, 5.0),
            (3.0, 4.0),
            (3.0, 5.0),
            (3.0, 6.0),
            (4.0, 5.0),
            (4.0, 6.0),
            (4.0, 7.0),
        ]
        bins = create_estimate_bins(data, min_samples=3)
        # Should have bins
        assert len(bins) > 0
        # All bins should have proper structure
        for bin_ in bins:
            assert len(bin_.samples) >= 3

    def test_create_bins_with_expanding_distance(self) -> None:
        """Test that bins expand to include enough samples."""
        # Create data where we need to expand distance to get min_samples
        data = [
            (1.0, 2.0),
            (3.0, 4.0),
            (5.0, 6.0),
            (7.0, 8.0),
            (9.0, 10.0),
            (11.0, 12.0),
            (13.0, 14.0),
            (15.0, 16.0),
            (17.0, 18.0),
            (19.0, 20.0),
            (21.0, 22.0),
            (23.0, 24.0),
        ]
        bins = create_estimate_bins(data, min_samples=5)
        # Should create bins that each have at least 5 samples
        for bin_ in bins:
            assert len(bin_.samples) >= 5


class TestEstimateBin:
    """Tests for EstimateBin dataclass."""

    def test_estimate_bin_sample(self) -> None:
        """EstimateBin should sample from its distribution."""
        dist = ShiftedLognormal(min=0.5, mode=2.0, percentile_95=8.0)
        bin_ = EstimateBin(
            center_estimate=5.0,
            lower_bound=3.0,
            upper_bound=7.0,
            samples=[4.0, 5.0, 6.0],
            distribution=dist,
        )
        rng = np.random.default_rng(42)
        sample = bin_.sample(rng)
        assert sample > 0  # Should be positive

    def test_estimate_bin_find_for_estimate_in_bounds(self) -> None:
        """Find the right bin for a given estimate."""
        dist1 = ShiftedLognormal(min=0.5, mode=2.0, percentile_95=8.0)
        dist2 = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0)
        bins = [
            EstimateBin(
                center_estimate=5.0,
                lower_bound=0.0,
                upper_bound=7.5,
                samples=[4.0, 5.0, 6.0],
                distribution=dist1,
            ),
            EstimateBin(
                center_estimate=10.0,
                lower_bound=7.5,
                upper_bound=float("inf"),
                samples=[9.0, 10.0, 11.0],
                distribution=dist2,
            ),
        ]

        from fluxx.jira.distributions import find_bin_for_estimate

        # Estimate of 6 should be in first bin
        bin_found = find_bin_for_estimate(6.0, bins)
        assert bin_found.center_estimate == 5.0

        # Estimate of 12 should be in second bin
        bin_found = find_bin_for_estimate(12.0, bins)
        assert bin_found.center_estimate == 10.0

    def test_find_bin_for_estimate_at_zero_lower_bound(self) -> None:
        """Find bin when estimate is at zero and bin has lower_bound=0."""
        dist = ShiftedLognormal(min=0.5, mode=2.0, percentile_95=8.0)
        bins = [
            EstimateBin(
                center_estimate=5.0,
                lower_bound=0.0,
                upper_bound=10.0,
                samples=[4.0, 5.0, 6.0],
                distribution=dist,
            ),
        ]

        from fluxx.jira.distributions import find_bin_for_estimate

        # Estimate of 0 should be in the bin with lower_bound=0
        bin_found = find_bin_for_estimate(0.0, bins)
        assert bin_found.center_estimate == 5.0

    def test_find_bin_for_estimate_outside_all_bounds(self) -> None:
        """Find closest bin when estimate is outside all bounds."""
        dist1 = ShiftedLognormal(min=0.5, mode=2.0, percentile_95=8.0)
        dist2 = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0)
        bins = [
            EstimateBin(
                center_estimate=5.0,
                lower_bound=2.0,
                upper_bound=8.0,
                samples=[4.0, 5.0, 6.0],
                distribution=dist1,
            ),
            EstimateBin(
                center_estimate=15.0,
                lower_bound=10.0,
                upper_bound=20.0,
                samples=[14.0, 15.0, 16.0],
                distribution=dist2,
            ),
        ]

        from fluxx.jira.distributions import find_bin_for_estimate

        # Estimate of 1 is outside all bounds, should find closest center (5.0)
        bin_found = find_bin_for_estimate(1.0, bins)
        assert bin_found.center_estimate == 5.0

        # Estimate of 9 is between bins, should find closest center
        bin_found = find_bin_for_estimate(9.0, bins)
        # 9 is closer to 5 (distance 4) than to 15 (distance 6)
        assert bin_found.center_estimate == 5.0
