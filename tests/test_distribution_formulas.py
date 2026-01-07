"""Tests for validating ShiftedLognormal distribution formulas.

These tests verify that:
1. convert_shifted_lognormal_params correctly recovers mu and sigma
2. fit_bin_distribution produces distributions that match the input data
3. fit_fallback_distribution produces distributions that match the input data
"""

import math

import numpy as np
import pytest

from fluxx.jira.distributions import fit_bin_distribution, fit_fallback_distribution
from fluxx.simulation.distributions import convert_shifted_lognormal_params

# Test parameter pairs: (u_mean, u_variance) for underlying normal
# These produce known theoretical mode, median, p95
TEST_PARAMS = [
    (math.log(1), math.log(2)),  # (0, 0.693...)
    (math.log(10), math.log(4)),  # (2.303..., 1.386...)
    (math.log(8), math.log(16)),  # (2.079..., 2.773...)
]


def theoretical_values(u_mean: float, u_variance: float) -> dict[str, float]:
    """Compute theoretical mode, median, p95 for lognormal with given params."""
    sigma = math.sqrt(u_variance)
    return {
        "median": math.exp(u_mean),
        "mode": math.exp(u_mean - u_variance),
        "p95": math.exp(u_mean + 1.645 * sigma),
    }


class TestConvertShiftedLognormalParams:
    """Test convert_shifted_lognormal_params recovers mu/sigma correctly."""

    def test_roundtrip_with_known_params(self) -> None:
        """Given theoretical (min=0, mode, p95), recover the original mu and sigma."""
        for u_mean, u_variance in TEST_PARAMS:
            sigma = math.sqrt(u_variance)
            theoretical = theoretical_values(u_mean, u_variance)

            # Input: min=0, mode and p95 from theoretical formulas
            recovered_shift, recovered_mu, recovered_sigma = (
                convert_shifted_lognormal_params(
                    min_val=0.0,
                    mode=theoretical["mode"],
                    p95=theoretical["p95"],
                )
            )

            assert abs(recovered_shift - 0.0) < 1e-10, (
                f"Expected shift=0, got {recovered_shift}"
            )
            assert abs(recovered_mu - u_mean) < 0.001, (
                f"Expected mu={u_mean:.6f}, got {recovered_mu:.6f}"
            )
            assert abs(recovered_sigma - sigma) < 0.001, (
                f"Expected sigma={sigma:.6f}, got {recovered_sigma:.6f}"
            )

    def test_with_nonzero_shift(self) -> None:
        """Test that shift is correctly handled."""
        shift = 5.0
        u_mean = math.log(10)
        u_variance = math.log(4)
        sigma = math.sqrt(u_variance)

        # Theoretical mode and p95 for unshifted distribution
        mode_unshifted = math.exp(u_mean - u_variance)
        p95_unshifted = math.exp(u_mean + 1.645 * sigma)

        # Shifted versions
        mode = shift + mode_unshifted
        p95 = shift + p95_unshifted

        recovered_shift, recovered_mu, recovered_sigma = (
            convert_shifted_lognormal_params(min_val=shift, mode=mode, p95=p95)
        )

        assert abs(recovered_shift - shift) < 1e-10
        assert abs(recovered_mu - u_mean) < 0.001
        assert abs(recovered_sigma - sigma) < 0.001

    def test_sampling_with_recovered_params_matches_theoretical(self) -> None:
        """Samples from recovered params should have expected statistics."""
        for u_mean, u_variance in TEST_PARAMS:
            theoretical = theoretical_values(u_mean, u_variance)

            shift, mu, sigma = convert_shifted_lognormal_params(
                min_val=0.0, mode=theoretical["mode"], p95=theoretical["p95"]
            )

            # Sample and check statistics
            rng = np.random.default_rng(42)
            samples = shift + rng.lognormal(mu, sigma, size=50_000)

            empirical_median = float(np.median(samples))
            empirical_p95 = float(np.percentile(samples, 95))

            # Allow 5% tolerance for sampling error
            assert (
                abs(empirical_median - theoretical["median"]) / theoretical["median"]
                < 0.05
            )
            assert abs(empirical_p95 - theoretical["p95"]) / theoretical["p95"] < 0.05


class TestFitBinDistribution:
    """Test fit_bin_distribution produces distributions matching input data."""

    def test_fit_from_lognormal_samples_zero_shift(self) -> None:
        """Fit samples from a lognormal with zero shift, verify parameters."""
        u_mean = math.log(10)
        u_variance = math.log(4)
        sigma = math.sqrt(u_variance)

        # Generate samples
        rng = np.random.default_rng(42)
        samples = rng.lognormal(mean=u_mean, sigma=sigma, size=1_000).tolist()

        # Fit with lower_bound=0 (forces loc=0)
        fitted = fit_bin_distribution(samples, lower_bound=0.0)

        # Verify min=0
        assert fitted.min == 0.0

        # Recover mu/sigma from fitted distribution
        _, recovered_mu, recovered_sigma = convert_shifted_lognormal_params(
            fitted.min, fitted.mode, fitted.percentile_95
        )

        # Should be close to original parameters (within fitting tolerance)
        assert abs(recovered_mu - u_mean) < 0.3, (
            f"Recovered mu={recovered_mu:.4f} too far from original {u_mean:.4f}"
        )
        assert abs(recovered_sigma - sigma) < 0.3, (
            f"Recovered sigma={recovered_sigma:.4f} too far from original {sigma:.4f}"
        )

    def test_samples_from_fitted_match_original_statistics(self) -> None:
        """Samples from fitted distribution should have similar stats to input."""
        u_mean = math.log(10)
        u_variance = math.log(2)
        sigma = math.sqrt(u_variance)

        rng = np.random.default_rng(42)
        original_samples = rng.lognormal(mean=u_mean, sigma=sigma, size=1_000).tolist()
        original_median = float(np.median(original_samples))
        original_p95 = float(np.percentile(original_samples, 95))

        # Fit distribution
        fitted = fit_bin_distribution(original_samples, lower_bound=0.0)

        # Sample from fitted distribution
        shift, mu, sig = convert_shifted_lognormal_params(
            fitted.min, fitted.mode, fitted.percentile_95
        )
        rng2 = np.random.default_rng(99)
        fitted_samples = shift + rng2.lognormal(mu, sig, size=1_000)

        fitted_median = float(np.median(fitted_samples))
        fitted_p95 = float(np.percentile(fitted_samples, 95))

        # Medians should be within 30% (fitting adds variance)
        assert abs(fitted_median - original_median) / original_median < 0.3
        # P95 should be within 50% (tails are harder to estimate)
        assert abs(fitted_p95 - original_p95) / original_p95 < 0.5


class TestFitFallbackDistribution:
    """Test fit_fallback_distribution produces reasonable distributions."""

    def test_fit_produces_valid_distribution(self) -> None:
        """Fitted distribution should have min < mode < p95."""
        rng = np.random.default_rng(42)
        samples = rng.lognormal(mean=2.0, sigma=0.8, size=500).tolist()

        fitted = fit_fallback_distribution(samples)

        assert fitted.min < fitted.mode < fitted.percentile_95, (
            f"Invalid ordering: min={fitted.min}, mode={fitted.mode}, "
            f"p95={fitted.percentile_95}"
        )
        assert fitted.min >= 0, "Fitted min should be non-negative"

    def test_samples_from_fitted_are_positive(self) -> None:
        """Samples from fitted distribution should all be positive."""
        rng = np.random.default_rng(42)
        samples = rng.lognormal(mean=1.5, sigma=1.0, size=500).tolist()

        fitted = fit_fallback_distribution(samples)

        shift, mu, sigma = convert_shifted_lognormal_params(
            fitted.min, fitted.mode, fitted.percentile_95
        )
        rng2 = np.random.default_rng(99)
        fitted_samples = shift + rng2.lognormal(mu, sigma, size=1_000)

        assert np.all(fitted_samples > 0)

    def test_single_value_edge_case(self) -> None:
        """Single value should produce valid distribution."""
        fitted = fit_fallback_distribution([10.0])

        assert fitted.min < fitted.mode < fitted.percentile_95
        assert fitted.min == pytest.approx(8.0)  # 0.8 * 10
        assert fitted.mode == pytest.approx(10.0)
        assert fitted.percentile_95 == pytest.approx(15.0)  # 1.5 * 10

    def test_identical_values_edge_case(self) -> None:
        """All identical values should produce valid distribution."""
        fitted = fit_fallback_distribution([5.0, 5.0, 5.0, 5.0, 5.0])

        assert fitted.min < fitted.mode < fitted.percentile_95
        assert fitted.min == pytest.approx(4.0)
        assert fitted.mode == pytest.approx(5.0)
        assert fitted.percentile_95 == pytest.approx(7.5)


class TestDistributionOrderingInvariants:
    """Test that min < mode < p95 is always maintained."""

    def test_wide_variance_distribution(self) -> None:
        """High variance distributions should still maintain ordering."""
        # High variance can push mode very close to 0
        rng = np.random.default_rng(42)
        # sigma=2 is very high variance
        samples = rng.lognormal(mean=2.0, sigma=2.0, size=500).tolist()

        fitted = fit_fallback_distribution(samples)
        assert fitted.min < fitted.mode < fitted.percentile_95

        fitted_bin = fit_bin_distribution(samples, lower_bound=0.0)
        assert fitted_bin.min < fitted_bin.mode < fitted_bin.percentile_95

    def test_narrow_variance_distribution(self) -> None:
        """Low variance distributions should still maintain ordering."""
        rng = np.random.default_rng(42)
        samples = rng.lognormal(mean=2.0, sigma=0.2, size=500).tolist()

        fitted = fit_fallback_distribution(samples)
        assert fitted.min < fitted.mode < fitted.percentile_95
