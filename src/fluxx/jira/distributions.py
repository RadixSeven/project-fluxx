"""Distribution fitting for Jira historical duration data.

This module provides functions to fit ShiftedLognormal distributions
to historical task duration data, supporting both simple fallback
distributions and bin-based conditional distributions keyed by estimates.
"""

from dataclasses import dataclass

import numpy as np
from scipy import stats

from fluxx.data.models import ShiftedLognormal
from fluxx.simulation.distributions import sample_shifted_lognormal


class InsufficientDataError(Exception):
    """Raised when there is not enough data to fit a distribution."""


@dataclass
class EstimateBin:
    """A bin of historical data grouped by original estimate.

    Attributes:
        center_estimate: The estimate value this bin is centered on
        lower_bound: Lower bound of estimates included (exclusive)
        upper_bound: Upper bound of estimates included (inclusive)
        samples: The actual duration times in this bin
        distribution: The fitted ShiftedLognormal for this bin
    """

    center_estimate: float
    lower_bound: float
    upper_bound: float
    samples: list[float]
    distribution: ShiftedLognormal

    def sample(self, rng: np.random.Generator) -> float:
        """Sample a duration from this bin's distribution.

        Args:
            rng: NumPy random generator

        Returns:
            Sampled duration value
        """
        return sample_shifted_lognormal(self.distribution, rng)


def fit_fallback_distribution(times: list[float]) -> ShiftedLognormal:
    """Fit a ShiftedLognormal distribution to a list of duration times.

    This is the "fallback" distribution used when no estimate is available
    or when there's not enough data for bin-based fitting.

    Args:
        times: List of historical duration times (in hours)

    Returns:
        A ShiftedLognormal distribution fitted to the data

    Raises:
        InsufficientDataError: If times is empty
    """
    if not times:
        raise InsufficientDataError("Cannot fit distribution with no data")

    times_array = np.array(times)

    # Handle edge case: all values identical or single value
    if len(times) == 1 or np.std(times_array) < 1e-10:
        value = float(times_array[0])
        # Create a minimal distribution centered around the value
        # For zero or negative values (shouldn't happen for durations), use defaults
        if value <= 0:
            return ShiftedLognormal(min=0.1, mode=0.2, percentile_95=1.0)
        # For positive values, constraints are automatically satisfied:
        # min = 0.8*value, mode = value > min, p95 = 1.5*value > mode
        return ShiftedLognormal(
            min=value * 0.8,
            mode=value,
            percentile_95=value * 1.5,
        )

    # Fit a 3-parameter lognormal: X = loc + exp(normal(s, scale))
    # scipy.stats.lognorm uses (s, loc, scale) where:
    # - s is the shape parameter (sigma of the underlying normal)
    # - loc is the shift (minimum value)
    # - scale is exp(mu) where mu is the mean of underlying normal

    # First, try to fit with loc (shift) constrained to be at or below min
    min_time = float(np.min(times_array))
    # Use a small shift to ensure positive values for log
    initial_shift = max(0, min_time * 0.8)

    # Shift data and fit a 2-parameter lognormal
    shifted_data = times_array - initial_shift
    # Ensure all shifted values are positive
    shifted_data = np.maximum(shifted_data, 1e-10)

    # Fit lognormal to shifted data
    shape, _, scale = stats.lognorm.fit(shifted_data, floc=0)

    # Convert to our parameterization:
    # loc (shift) = initial_shift
    # mu (mean of underlying normal) = log(scale)
    # sigma (std of underlying normal) = shape
    loc = initial_shift
    mu = np.log(scale)
    sigma = shape

    # Calculate mode and p95 from fitted parameters
    # For lognormal: mode = exp(mu - sigma^2)
    # For shifted: mode = loc + exp(mu - sigma^2)
    min_val = float(loc)
    mode_unshifted = np.exp(mu - sigma**2)
    # Ensure mode > min_val (mathematically guaranteed, but use max for robustness)
    mode = max(min_val + 0.01, float(loc + mode_unshifted))

    # p95 = loc + exp(mu + 1.645 * sigma)
    # Ensure p95 > mode (mathematically guaranteed, but use max for robustness)
    p95 = max(mode * 1.5, float(loc + np.exp(mu + 1.645 * sigma)))

    return ShiftedLognormal(min=min_val, mode=mode, percentile_95=p95)


def fit_bin_distribution(
    data: list[float],
    lower_bound: float,
) -> ShiftedLognormal:
    """Fit a ShiftedLognormal distribution to bin data.

    Args:
        data: List of actual duration times in the bin
        lower_bound: Lower bound for the distribution's location parameter.
            If 0, fits with loc=0 (no shift). Otherwise, allows shift.

    Returns:
        A ShiftedLognormal distribution fitted to the data

    Raises:
        InsufficientDataError: If data is empty
    """
    if not data:
        raise InsufficientDataError("Cannot fit distribution with no data")

    times_array = np.array(data)

    # Handle edge case: all values identical
    if np.std(times_array) < 1e-10:
        value = float(times_array[0])
        # Use lower_bound as min, ensure mode and p95 are valid
        min_val = max(lower_bound, 0.0)
        # Ensure mode > min_val
        mode = max(min_val + 0.01, value, min_val * 1.1 if min_val > 0 else 0.1)
        # Ensure p95 > mode
        p95 = max(mode * 1.5, mode + 0.01)
        return ShiftedLognormal(min=min_val, mode=mode, percentile_95=p95)

    # Determine the shift (loc) parameter
    # For zero lower bound, fit with floc=0; otherwise use lower_bound
    initial_shift = 0.0 if lower_bound == 0.0 else lower_bound

    # Shift data and fit
    shifted_data = times_array - initial_shift
    # Ensure all shifted values are positive
    shifted_data = np.maximum(shifted_data, 1e-10)

    # Fit lognormal to shifted data
    shape, _, scale = stats.lognorm.fit(shifted_data, floc=0)

    # Convert parameters
    loc = initial_shift
    mu = np.log(scale)
    sigma = shape

    # Calculate mode and p95
    min_val = float(loc)
    mode_unshifted = np.exp(mu - sigma**2)
    # Ensure mode > min_val (mathematically guaranteed, but use max for robustness)
    mode = max(min_val + 0.01, float(loc + mode_unshifted))
    # Ensure p95 > mode (mathematically guaranteed, but use max for robustness)
    p95 = max(mode * 1.5, float(loc + np.exp(mu + 1.645 * sigma)))

    return ShiftedLognormal(min=min_val, mode=mode, percentile_95=p95)


def create_estimate_bins(
    data: list[tuple[float, float]],
    min_samples: int = 30,
) -> list[EstimateBin]:
    """Create bins of historical data grouped by original estimate.

    Each bin contains at least min_samples entries. Bins are centered on
    unique estimate values and expand outward until they contain enough
    samples.

    Args:
        data: List of (estimate, actual_time) tuples
        min_samples: Minimum number of samples per bin

    Returns:
        List of EstimateBin objects with fitted distributions
    """
    if not data:
        return []

    # Sort by estimate
    sorted_data = sorted(data, key=lambda x: x[0])
    estimates = [d[0] for d in sorted_data]
    times = [d[1] for d in sorted_data]

    # If total data < min_samples, create one bin
    if len(data) < min_samples:
        all_times = [t for _, t in data]
        dist = fit_fallback_distribution(all_times)
        min_est = min(estimates)
        max_est = max(estimates)
        return [
            EstimateBin(
                center_estimate=(min_est + max_est) / 2,
                lower_bound=0.0,
                upper_bound=float("inf"),
                samples=all_times,
                distribution=dist,
            )
        ]

    # Get unique estimates as potential bin centers
    unique_estimates = sorted(set(estimates))

    # Create bins for each unique estimate
    bins: list[EstimateBin] = []
    min_estimate = min(estimates)
    max_estimate = max(estimates)

    for center in unique_estimates:
        # Find samples within expanding distance until we have min_samples
        bin_samples: list[float] = []
        included_estimates: list[float] = []
        excluded_below: float | None = None
        excluded_above: float | None = None

        # Sort estimates by distance from center
        indexed_by_dist = sorted(
            range(len(estimates)), key=lambda i: abs(estimates[i] - center)
        )

        for i in indexed_by_dist:
            if len(bin_samples) >= min_samples:
                # Record the first excluded estimate on each side
                est = estimates[i]
                if est < center and (excluded_below is None or est > excluded_below):
                    excluded_below = est
                elif est > center and (excluded_above is None or est < excluded_above):
                    excluded_above = est
            else:
                bin_samples.append(times[i])
                included_estimates.append(estimates[i])

        # bin_samples is always non-empty because we add samples until min_samples
        # or until we exhaust indexed_by_dist (which has at least len(data) entries)

        # Calculate bounds as midpoints between included and excluded
        min_included = min(included_estimates)
        max_included = max(included_estimates)

        # Lower bound: 0 if at minimum, else midpoint to nearest excluded below.
        # When min_included != min_estimate, excluded_below is always set because
        # any estimate below min_included would have been processed and excluded.
        lower_bound = 0.0
        if min_included != min_estimate and excluded_below is not None:
            lower_bound = (excluded_below + min_included) / 2

        # Upper bound: inf if at maximum, else midpoint to nearest excluded above.
        # When max_included != max_estimate, excluded_above is always set because
        # any estimate above max_included would have been processed and excluded.
        upper_bound = float("inf")
        if max_included != max_estimate and excluded_above is not None:
            upper_bound = (max_included + excluded_above) / 2

        # Fit distribution to bin samples
        dist = fit_bin_distribution(bin_samples, lower_bound)

        bins.append(
            EstimateBin(
                center_estimate=center,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                samples=bin_samples,
                distribution=dist,
            )
        )

    # If we created multiple bins with overlapping ranges, deduplicate
    # by keeping bins with distinct lower/upper bounds
    if len(bins) > 1:
        bins = _deduplicate_bins(bins)

    return bins


def _deduplicate_bins(bins: list[EstimateBin]) -> list[EstimateBin]:
    """Remove bins with identical sample sets.

    Keeps the first bin encountered with each unique sample set.
    """
    seen_samples: dict[tuple[float, ...], EstimateBin] = {}
    for bin_ in bins:
        key = tuple(sorted(bin_.samples))
        if key not in seen_samples:
            seen_samples[key] = bin_
    return list(seen_samples.values())


def find_bin_for_estimate(
    estimate: float,
    bins: list[EstimateBin],
) -> EstimateBin:
    """Find the appropriate bin for a given estimate.

    Args:
        estimate: The original estimate value
        bins: List of available bins

    Returns:
        The bin whose range contains the estimate, or the nearest bin
        if the estimate is outside all ranges.
    """
    # First, try to find a bin where estimate is within bounds
    for bin_ in bins:
        if bin_.lower_bound < estimate <= bin_.upper_bound:
            return bin_
        # Also check if it's at exactly the lower bound with lower_bound=0
        if bin_.lower_bound == 0.0 and estimate == 0.0:
            return bin_

    # If not found, return the bin with the closest center
    return min(bins, key=lambda b: abs(b.center_estimate - estimate))
