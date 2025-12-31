"""Distribution sampling utilities for simulation."""

import numpy as np

from fluxx.data.models import DurationDistribution, ShiftedLognormal, Triangular


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
    for _ in range(max_attempts):
        if isinstance(dist, ShiftedLognormal):
            sample = sample_shifted_lognormal(dist, rng)
        elif isinstance(dist, Triangular):
            sample = sample_triangular(dist, rng)
        else:
            raise ValueError(f"Unknown distribution type: {type(dist)}")

        if sample >= min_value:
            return sample

    # Fallback: approximate conditional distribution of tail with exponential
    # P(X | X >= e) ≈ e + Exp(λ) where λ = 1/mean_of_original
    mean_original = estimate_mean(dist)
    lambda_rate = 1.0 / mean_original
    tail_sample = rng.exponential(scale=1.0 / lambda_rate)
    return min_value + tail_sample
