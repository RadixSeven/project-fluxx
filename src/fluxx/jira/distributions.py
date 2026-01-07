"""Distribution fitting for Jira historical duration data.

This module provides functions for empirical bin-based duration sampling
from historical task duration data. Tasks are grouped into bins by estimate,
and sampling is done by randomly selecting from historical (estimate, actual)
pairs within a bin.
"""

from dataclasses import dataclass

import numpy as np


class InsufficientDataError(Exception):
    """Raised when there is not enough data to fit a distribution."""


@dataclass
class EmpiricalEstimateBin:
    """A bin containing historical (estimate, actual) pairs for empirical sampling.

    Unlike fitted distributions, this stores raw pairs and samples directly
    from them, preserving the actual historical variation.

    Attributes:
        center_estimate: The estimate value this bin is centered on (in hours)
        lower_bound: Lower bound of estimates included (exclusive, in hours)
        upper_bound: Upper bound of estimates included (inclusive, in hours)
        samples: List of (estimate_hours, actual_hours) pairs in this bin
    """

    center_estimate: float
    lower_bound: float
    upper_bound: float
    samples: list[tuple[float, float]]

    def sample(self, rng: np.random.Generator) -> float:
        """Randomly select an actual duration from this bin's samples.

        Args:
            rng: NumPy random generator

        Returns:
            Sampled actual duration in hours
        """
        index = rng.integers(0, len(self.samples))
        return self.samples[index][1]  # Return the actual duration

    def sample_filtered(
        self, rng: np.random.Generator, min_duration: float
    ) -> float | None:
        """Sample from filtered bin where actual > min_duration.

        Args:
            rng: NumPy random generator
            min_duration: Minimum duration threshold (exclusive)

        Returns:
            Sampled actual duration, or None if no samples exceed threshold
        """
        valid_samples = [s for s in self.samples if s[1] > min_duration]
        if not valid_samples:
            return None
        index = rng.integers(0, len(valid_samples))
        return valid_samples[index][1]


def create_empirical_bins(
    data: list[tuple[float, float]],
    min_samples: int = 30,
) -> list[EmpiricalEstimateBin]:
    """Create bins of historical data grouped by original estimate.

    Each bin contains at least min_samples entries. Bins are centered on
    unique estimate values and expand outward until they contain enough
    samples. Unlike fitted bins, these store raw (estimate, actual) pairs.

    Args:
        data: List of (estimate_hours, actual_hours) tuples
        min_samples: Minimum number of samples per bin

    Returns:
        List of EmpiricalEstimateBin objects containing raw sample pairs
    """
    if not data:
        return []

    # Sort by estimate
    sorted_data = sorted(data, key=lambda x: x[0])
    estimates = [d[0] for d in sorted_data]

    # If total data < min_samples, create one bin with all data
    if len(data) < min_samples:
        min_est = min(estimates)
        max_est = max(estimates)
        return [
            EmpiricalEstimateBin(
                center_estimate=(min_est + max_est) / 2,
                lower_bound=0.0,
                upper_bound=float("inf"),
                samples=list(data),  # Store all (estimate, actual) pairs
            )
        ]

    # Get unique estimates as potential bin centers
    unique_estimates = sorted(set(estimates))

    # Create bins for each unique estimate
    bins: list[EmpiricalEstimateBin] = []
    min_estimate = min(estimates)
    max_estimate = max(estimates)

    for center in unique_estimates:
        # Find samples within expanding distance until we have min_samples
        bin_samples: list[tuple[float, float]] = []
        included_estimates: list[float] = []
        excluded_below: float | None = None
        excluded_above: float | None = None

        # Sort by distance from center
        indexed_by_dist = sorted(
            range(len(sorted_data)), key=lambda i: abs(estimates[i] - center)
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
                bin_samples.append(sorted_data[i])
                included_estimates.append(estimates[i])

        # Calculate bounds as midpoints between included and excluded
        min_included = min(included_estimates)
        max_included = max(included_estimates)

        lower_bound = 0.0
        if min_included != min_estimate and excluded_below is not None:
            lower_bound = (excluded_below + min_included) / 2

        upper_bound = float("inf")
        if max_included != max_estimate and excluded_above is not None:
            upper_bound = (max_included + excluded_above) / 2

        bins.append(
            EmpiricalEstimateBin(
                center_estimate=center,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                samples=bin_samples,
            )
        )

    # Deduplicate bins with identical sample sets
    if len(bins) > 1:
        bins = _deduplicate_empirical_bins(bins)

    return bins


def _deduplicate_empirical_bins(
    bins: list[EmpiricalEstimateBin],
) -> list[EmpiricalEstimateBin]:
    """Remove bins with identical sample sets.

    Keeps the first bin encountered with each unique sample set.
    """
    seen_samples: dict[tuple[tuple[float, float], ...], EmpiricalEstimateBin] = {}
    for bin_ in bins:
        key = tuple(sorted(bin_.samples))
        if key not in seen_samples:
            seen_samples[key] = bin_
    return list(seen_samples.values())


def find_empirical_bin_for_estimate(
    estimate: float,
    bins: list[EmpiricalEstimateBin],
) -> EmpiricalEstimateBin:
    """Find the appropriate bin for a given estimate.

    When equidistant from two bins, prefers the higher estimate bin
    (conservative approach).

    Args:
        estimate: The original estimate value (in hours)
        bins: List of available bins

    Returns:
        The bin whose range contains the estimate, or the nearest bin
        (preferring higher when equidistant).
    """
    # First, try to find a bin where estimate is within bounds
    for bin_ in bins:
        if bin_.lower_bound < estimate <= bin_.upper_bound:
            return bin_
        # Also check if it's at exactly the lower bound with lower_bound=0
        if bin_.lower_bound == 0.0 and estimate == 0.0:
            return bin_

    # If not found, return the bin with the closest center
    # When equidistant, prefer higher center (conservative)
    def distance_key(b: EmpiricalEstimateBin) -> tuple[float, float]:
        dist = abs(b.center_estimate - estimate)
        # Negative center so higher centers sort first when distances are equal
        return (dist, -b.center_estimate)

    return min(bins, key=distance_key)
