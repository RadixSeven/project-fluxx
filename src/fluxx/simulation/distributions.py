"""Distribution sampling utilities for simulation."""

import logging
from dataclasses import dataclass

import numpy as np

from fluxx.data.models import (
    DurationDistribution,
    JiraDurationDistribution,
    Project,
    ShiftedLognormal,
    Triangular,
)
from fluxx.jira.distributions import (
    EmpiricalEstimateBin,
    create_empirical_bins,
    find_empirical_bin_for_estimate,
)

logger = logging.getLogger(__name__)


def convert_shifted_lognormal_params(
    min_val: float, mode: float, p95: float
) -> tuple[float, float, float]:
    """Convert ShiftedLognormal parameters to (shift, mu, sigma) for numpy.

    For a shifted lognormal: X = shift + exp(normal(mu, sigma))

    Mathematical relationships:
    - shift = min_val (the minimum value)
    - mode - shift = exp(mu - sigma^2) [mode of lognormal]
    - p95 - shift = exp(mu + 1.645 * sigma) [95th percentile, 1.645 is z-score]

    Args:
        min_val: Minimum value of the distribution
        mode: Most likely value (mode)
        p95: 95th percentile value

    Returns:
        Tuple of (shift, mu, sigma) where samples are:
        shift + numpy.random.lognormal(mu, sigma)
    """
    shift = min_val
    mode_unshifted = mode - shift
    p95_unshifted = p95 - shift

    # From mode: exp(mu - sigma^2) = mode_unshifted
    # From p95:  exp(mu + 1.645*sigma) = p95_unshifted
    #
    # Taking log:
    # mu - sigma^2 = ln(mode_unshifted)  ... (1)
    # mu + 1.645*sigma = ln(p95_unshifted)  ... (2)
    #
    # From (2) - (1):
    # sigma^2 + 1.645*sigma = ln(p95_unshifted) - ln(mode_unshifted)
    #
    # Quadratic equation: sigma^2 + 1.645*sigma - ln(p95/mode) = 0

    ln_ratio = np.log(p95_unshifted / mode_unshifted)

    # Solve quadratic: sigma^2 + 1.645*sigma - ln_ratio = 0
    # Using quadratic formula: sigma = (-b +/- sqrt(b^2 - 4ac)) / 2a
    # We want the positive root
    a = 1.0
    b = 1.645
    c = -ln_ratio

    discriminant = b**2 - 4 * a * c
    sigma = (-b + np.sqrt(discriminant)) / (2 * a)

    # From equation (1):
    mu = np.log(mode_unshifted) + sigma**2

    return shift, mu, sigma


def estimate_mean(dist: DurationDistribution) -> float:
    """Estimate the mean of a distribution for tail approximation.

    Args:
        dist: The duration distribution

    Returns:
        Estimated mean value
    """
    if isinstance(dist, ShiftedLognormal):
        # For lognormal: mean = exp(mu + sigma^2/2)
        # For shifted: mean = shift + exp(mu + sigma^2/2)
        shift, mu, sigma = convert_shifted_lognormal_params(
            dist.min, dist.mode, dist.percentile_95
        )
        return float(shift + np.exp(mu + sigma**2 / 2))
    elif isinstance(dist, Triangular):
        # For triangular: mean = (min + mode + max) / 3
        return (dist.min + dist.mode + dist.max) / 3.0
    else:
        raise ValueError(f"Unknown distribution type: {type(dist)}")


def sample_shifted_lognormal(dist: ShiftedLognormal, rng: np.random.Generator) -> float:
    """Sample from a ShiftedLognormal distribution.

    Args:
        dist: ShiftedLognormal distribution parameters
        rng: NumPy random generator

    Returns:
        A sample from the distribution
    """
    shift, mu, sigma = convert_shifted_lognormal_params(
        dist.min, dist.mode, dist.percentile_95
    )
    return shift + rng.lognormal(mu, sigma)


def sample_triangular(dist: Triangular, rng: np.random.Generator) -> float:
    """Sample from a Triangular distribution.

    Args:
        dist: Triangular distribution parameters
        rng: NumPy random generator

    Returns:
        A sample from the distribution
    """
    return float(rng.triangular(dist.min, dist.mode, dist.max))


def sample_with_rejection(
    dist: DurationDistribution,
    rng: np.random.Generator,
    min_value: float,
    max_attempts: int = 1000,
) -> float:
    """Sample from distribution with rejection sampling.

    Keep sampling until we get a value >= min_value.
    This ensures the sampled duration is consistent with already-elapsed time.

    If rejection sampling fails after max_attempts (elapsed time way in tail),
    approximate the conditional distribution with an exponential.

    Args:
        dist: The duration distribution
        rng: NumPy random generator
        min_value: Minimum acceptable value (elapsed time)
        max_attempts: Maximum rejection sampling attempts before fallback

    Returns:
        A sample >= min_value
    """
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        if isinstance(dist, ShiftedLognormal):
            sample = sample_shifted_lognormal(dist, rng)
        elif isinstance(dist, Triangular):
            sample = sample_triangular(dist, rng)
        else:
            raise ValueError(f"Unknown distribution type: {type(dist)}")

        if sample >= min_value:
            if attempts > 10:
                logger.debug(
                    "Rejection sampling took %d attempts for min_value=%.2f",
                    attempts,
                    min_value,
                )
            return sample

    # Fallback: approximate conditional distribution of tail with exponential
    # P(X | X >= e) ≈ e + Exp(λ) where λ = 1/mean_of_original
    mean_original = estimate_mean(dist)
    lambda_rate = 1.0 / mean_original
    tail_sample = rng.exponential(scale=1.0 / lambda_rate)

    logger.debug(
        "Rejection sampling exhausted after %d attempts, using exponential fallback: "
        "min_value=%.2f, result=%.2f",
        max_attempts,
        min_value,
        min_value + tail_sample,
    )

    return min_value + tail_sample


# Jira empirical distribution sampling


@dataclass
class JiraSamplingContext:
    """Context for sampling from JiraDurationDistribution.

    Pre-computed bins from historical Jira data, built once per simulation.
    The bins contain (estimate_hours, actual_hours) pairs for empirical sampling.

    Attributes:
        bins: Pre-computed empirical estimate bins
        all_actuals: All actual durations for fallback when no estimate
    """

    bins: list[EmpiricalEstimateBin]
    all_actuals: list[float]


def build_jira_sampling_context(project: Project) -> JiraSamplingContext:
    """Build sampling context from project's Jira history.

    Extracts historical (estimate, actual) pairs from the project's
    Jira configuration and creates empirical bins for sampling.

    Args:
        project: The project containing Jira history

    Returns:
        JiraSamplingContext with pre-computed bins
    """
    data: list[tuple[float, float]] = []
    all_actuals: list[float] = []

    # Extract data from Jira history
    if project.jira_config and project.jira_config.sync_metadata:
        for entry in project.jira_config.sync_metadata.history_entries:
            # Need both estimate and actual
            if (
                entry.original_estimate_seconds is not None
                and entry.total_logged_time_seconds is not None
                and entry.total_logged_time_seconds > 0
            ):
                estimate_hours = entry.original_estimate_seconds / 3600.0
                actual_hours = entry.total_logged_time_seconds / 3600.0
                data.append((estimate_hours, actual_hours))
                all_actuals.append(actual_hours)
            elif (
                entry.total_logged_time_seconds is not None
                and entry.total_logged_time_seconds > 0
            ):
                # No estimate, but have actual - use for fallback
                actual_hours = entry.total_logged_time_seconds / 3600.0
                all_actuals.append(actual_hours)

    # Create bins from historical data
    bins = create_empirical_bins(data, min_samples=30)

    return JiraSamplingContext(bins=bins, all_actuals=all_actuals)


def sample_jira_duration(
    dist: JiraDurationDistribution,
    context: JiraSamplingContext,
    rng: np.random.Generator,
) -> float:
    """Sample duration from JiraDurationDistribution using empirical bins.

    Algorithm:
    1. If task has estimate, find bin with closest center, sample from it
    2. If no estimate, sample from all historical actuals (fallback)
    3. If no history at all, use exponential distribution with mean = estimate

    Args:
        dist: The JiraDurationDistribution containing task's estimate data
        context: Pre-computed sampling context with bins
        rng: Random number generator

    Returns:
        Sampled duration in hours
    """
    estimate_hours: float | None = None
    if dist.original_estimate_seconds is not None:
        estimate_hours = dist.original_estimate_seconds / 3600.0

    # Case 1: Have estimate and bins - use bin-based sampling
    if estimate_hours is not None and context.bins:
        bin_ = find_empirical_bin_for_estimate(estimate_hours, context.bins)
        return bin_.sample(rng)

    # Case 2: No estimate but have history - sample from all actuals
    if context.all_actuals:
        index = rng.integers(0, len(context.all_actuals))
        return context.all_actuals[index]

    # Case 3: No history at all - use exponential with mean = estimate (or default)
    if estimate_hours is not None and estimate_hours > 0:
        return float(rng.exponential(scale=estimate_hours))
    else:
        # No estimate and no history - use default 8 hours
        return float(rng.exponential(scale=8.0))


def sample_jira_duration_filtered(
    dist: JiraDurationDistribution,
    context: JiraSamplingContext,
    rng: np.random.Generator,
    min_duration: float,
) -> float:
    """Sample duration for in-progress task using filtered sampling.

    For tasks with elapsed time, we need durations > min_duration.
    Uses filtered sampling (not rejection) for efficiency:
    1. Filter bin to values > min_duration, sample if any exist
    2. If filtered bin empty, filter all history > min_duration
    3. If all history exhausted, return min_duration + exponential sample

    Args:
        dist: The JiraDurationDistribution
        context: Pre-computed sampling context
        rng: Random number generator
        min_duration: Minimum acceptable duration (hours already logged)

    Returns:
        Sampled duration in hours, guaranteed >= min_duration
    """
    estimate_hours: float | None = None
    if dist.original_estimate_seconds is not None:
        estimate_hours = dist.original_estimate_seconds / 3600.0

    # Try bin-based filtered sampling first
    if estimate_hours is not None and context.bins:
        bin_ = find_empirical_bin_for_estimate(estimate_hours, context.bins)
        sample = bin_.sample_filtered(rng, min_duration)
        if sample is not None:
            return sample

    # Try filtered sampling from all actuals
    if context.all_actuals:
        valid_samples = [s for s in context.all_actuals if s > min_duration]
        if valid_samples:
            index = rng.integers(0, len(valid_samples))
            return valid_samples[index]

    # All history exhausted - return min_duration + exponential
    mean = estimate_hours if estimate_hours and estimate_hours > 0 else 8.0
    tail_sample = rng.exponential(scale=mean)
    return min_duration + tail_sample
