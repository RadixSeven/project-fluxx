"""Tests for distribution sampling functions."""

from datetime import UTC, datetime

import numpy as np

from fluxx.data.id_generation import generate_dag_id, generate_dag_version_id
from fluxx.data.models import (
    DAG,
    JiraDurationDistribution,
    Project,
    ProjectMetadata,
    ShiftedLognormal,
    Triangular,
)
from fluxx.jira.models import (
    JiraConfig,
    JiraDurationHistoryEntry,
    JiraIssueKey,
    JiraSyncMetadata,
)
from fluxx.simulation.distributions import (
    JiraSamplingContext,
    build_jira_sampling_context,
    convert_shifted_lognormal_params,
    estimate_mean,
    sample_jira_duration,
    sample_jira_duration_filtered,
    sample_shifted_lognormal,
    sample_triangular,
    sample_with_rejection,
)


def test_convert_shifted_lognormal_params() -> None:
    """Test ShiftedLognormal parameter conversion."""
    min_val = 1.0
    mode = 5.0
    p95 = 10.0

    shift, mu, sigma = convert_shifted_lognormal_params(min_val, mode, p95)

    # Shift should equal minimum
    assert shift == min_val

    # Verify the mode relationship: mode = shift + exp(mu - sigma^2)
    computed_mode = shift + np.exp(mu - sigma**2)
    assert abs(computed_mode - mode) < 0.01

    # Verify p95 relationship: p95 = shift + exp(mu + 1.645*sigma)
    computed_p95 = shift + np.exp(mu + 1.645 * sigma)
    assert abs(computed_p95 - p95) < 0.01


def test_shifted_lognormal_samples_above_min() -> None:
    """Test that ShiftedLognormal samples are always >= min."""
    dist = ShiftedLognormal(min=2.0, mode=5.0, percentile_95=15.0)
    rng = np.random.default_rng(seed=42)

    samples = [sample_shifted_lognormal(dist, rng) for _ in range(1000)]

    # All samples should be >= min
    assert all(s >= dist.min for s in samples)

    # Mean should be reasonable (within expected range)
    mean = np.mean(samples)
    assert 4.0 < mean < 10.0


def test_triangular_samples_in_range() -> None:
    """Test that Triangular samples are in [min, max]."""
    dist = Triangular(min=1.0, mode=3.0, max=8.0)
    rng = np.random.default_rng(seed=42)

    samples = [sample_triangular(dist, rng) for _ in range(1000)]

    # All samples should be in [min, max]
    assert all(dist.min <= s <= dist.max for s in samples)

    # Mean should be close to (min + mode + max) / 3
    mean = np.mean(samples)
    expected_mean = (dist.min + dist.mode + dist.max) / 3.0
    assert abs(mean - expected_mean) < 0.5


def test_rejection_sampling_above_threshold() -> None:
    """Test that rejection sampling produces values >= threshold."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    rng = np.random.default_rng(seed=42)

    threshold = 7.0
    samples = [sample_with_rejection(dist, rng, threshold) for _ in range(100)]

    # All samples should be >= threshold
    assert all(s >= threshold for s in samples)


def test_rejection_sampling_with_min_threshold() -> None:
    """Test rejection sampling when threshold equals min."""
    dist = ShiftedLognormal(min=2.0, mode=5.0, percentile_95=15.0)
    rng = np.random.default_rng(seed=42)

    # Threshold at minimum should work like normal sampling
    samples = [sample_with_rejection(dist, rng, dist.min) for _ in range(100)]

    assert all(s >= dist.min for s in samples)


def test_rejection_sampling_tail_fallback() -> None:
    """Test rejection sampling fallback with threshold way in tail."""
    dist = Triangular(min=1.0, mode=3.0, max=5.0)
    rng = np.random.default_rng(seed=42)

    # Threshold way beyond max will trigger exponential fallback
    threshold = 100.0
    sample = sample_with_rejection(dist, rng, threshold, max_attempts=10)

    # Should use exponential approximation
    assert sample >= threshold
    # Should be reasonably close to threshold (not astronomically large)
    assert sample < threshold * 3


def test_estimate_mean_shifted_lognormal() -> None:
    """Test mean estimation for ShiftedLognormal."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0)
    mean = estimate_mean(dist)

    # Mean should be greater than mode for lognormal
    assert mean > dist.mode
    # Should be reasonable value
    assert 5.0 < mean < 20.0


def test_estimate_mean_triangular() -> None:
    """Test mean estimation for Triangular."""
    dist = Triangular(min=1.0, mode=3.0, max=8.0)
    mean = estimate_mean(dist)

    # Mean should be (min + mode + max) / 3
    expected = (dist.min + dist.mode + dist.max) / 3.0
    assert abs(mean - expected) < 0.01


def test_shifted_lognormal_deterministic() -> None:
    """Test that seeded RNG produces deterministic results."""
    dist = ShiftedLognormal(min=1.0, mode=5.0, percentile_95=15.0)

    rng1 = np.random.default_rng(seed=123)
    rng2 = np.random.default_rng(seed=123)

    sample1 = sample_shifted_lognormal(dist, rng1)
    sample2 = sample_shifted_lognormal(dist, rng2)

    assert sample1 == sample2


def test_triangular_deterministic() -> None:
    """Test that seeded RNG produces deterministic results."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)

    rng1 = np.random.default_rng(seed=456)
    rng2 = np.random.default_rng(seed=456)

    sample1 = sample_triangular(dist, rng1)
    sample2 = sample_triangular(dist, rng2)

    assert sample1 == sample2


def test_rejection_sampling_deterministic() -> None:
    """Test that rejection sampling is deterministic with seeded RNG."""
    dist = Triangular(min=1.0, mode=5.0, max=10.0)
    threshold = 6.0

    rng1 = np.random.default_rng(seed=789)
    rng2 = np.random.default_rng(seed=789)

    sample1 = sample_with_rejection(dist, rng1, threshold)
    sample2 = sample_with_rejection(dist, rng2, threshold)

    assert sample1 == sample2


def test_estimate_mean_unknown_distribution() -> None:
    """Test that estimate_mean raises error for unknown distribution type."""
    import pytest

    from fluxx.data.models import DurationDistribution

    # Create a mock unknown distribution
    class UnknownDistribution(DurationDistribution):
        value: float = 1.0

    unknown_dist = UnknownDistribution(value=5.0)

    with pytest.raises(ValueError, match="Unknown distribution type"):
        estimate_mean(unknown_dist)


def test_sample_with_rejection_unknown_distribution() -> None:
    """Test that sample_with_rejection raises error for unknown distribution."""
    import pytest

    from fluxx.data.models import DurationDistribution

    # Create a mock unknown distribution
    class UnknownDistribution(DurationDistribution):
        value: float = 1.0

    unknown_dist = UnknownDistribution(value=5.0)
    rng = np.random.default_rng(seed=123)

    with pytest.raises(ValueError, match="Unknown distribution type"):
        sample_with_rejection(unknown_dist, rng, 0.0)


# Tests for Jira empirical distribution sampling


def make_history_entry(
    issue_number: int,
    estimate_seconds: int | None,
    actual_seconds: int,
) -> JiraDurationHistoryEntry:
    """Create a test history entry."""
    return JiraDurationHistoryEntry(
        server_url="https://jira.example.com",
        issue_key=JiraIssueKey(project_key="TEST", issue_number=issue_number),
        original_estimate_seconds=estimate_seconds,
        total_logged_time_seconds=actual_seconds,
        worker_jira_id="user1",
        issue_type="Story",
    )


def make_project_with_history(
    entries: list[JiraDurationHistoryEntry],
) -> Project:
    """Create a project with Jira history."""
    dag = DAG(
        id=generate_dag_id(),
        current_version_id=generate_dag_version_id(),
        node_map={},
    )
    now = datetime.now(UTC)
    return Project(
        version="1.3",
        metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
        dag=dag,
        persistent_tasks={},
        persistent_branches={},
        workers=[],
        simulations=[],
        jira_config=JiraConfig(
            server_url="https://jira.example.com",
            sync_metadata=JiraSyncMetadata(
                server_url="https://jira.example.com",
                last_history_sync=now,
                history_entries=entries,
            ),
        ),
    )


class TestBuildJiraSamplingContext:
    """Tests for build_jira_sampling_context."""

    def test_build_context_from_history(self) -> None:
        """Builds context from project history entries."""
        entries = [
            make_history_entry(1, 3600, 7200),  # 1h estimate, 2h actual
            make_history_entry(2, 3600, 5400),  # 1h estimate, 1.5h actual
            make_history_entry(3, 7200, 10800),  # 2h estimate, 3h actual
        ]
        project = make_project_with_history(entries)

        context = build_jira_sampling_context(project)

        # Should have extracted all actuals
        assert len(context.all_actuals) == 3
        assert 2.0 in context.all_actuals  # 7200 / 3600
        assert 1.5 in context.all_actuals  # 5400 / 3600
        assert 3.0 in context.all_actuals  # 10800 / 3600

    def test_build_context_includes_no_estimate_actuals(self) -> None:
        """Actuals without estimates go into all_actuals for fallback."""
        entries = [
            make_history_entry(1, None, 7200),  # No estimate, 2h actual
            make_history_entry(2, 3600, 5400),  # 1h estimate, 1.5h actual
        ]
        project = make_project_with_history(entries)

        context = build_jira_sampling_context(project)

        # All actuals should include both
        assert len(context.all_actuals) == 2
        assert 2.0 in context.all_actuals
        assert 1.5 in context.all_actuals

    def test_build_context_empty_history(self) -> None:
        """Empty history creates empty context."""
        project = make_project_with_history([])

        context = build_jira_sampling_context(project)

        assert context.bins == []
        assert context.all_actuals == []

    def test_build_context_no_jira_config(self) -> None:
        """Project without Jira config creates empty context."""
        dag = DAG(
            id=generate_dag_id(),
            current_version_id=generate_dag_version_id(),
            node_map={},
        )
        now = datetime.now(UTC)
        project = Project(
            version="1.3",
            metadata=ProjectMetadata(name="Test", created=now, last_modified=now),
            dag=dag,
            persistent_tasks={},
            persistent_branches={},
            workers=[],
            simulations=[],
            jira_config=None,
        )

        context = build_jira_sampling_context(project)

        assert context.bins == []
        assert context.all_actuals == []


class TestSampleJiraDuration:
    """Tests for sample_jira_duration."""

    def test_sample_with_estimate_and_bins(self) -> None:
        """Uses bin-based sampling when estimate and bins exist."""
        # Create enough history for bin creation (need 30+ for meaningful bins)
        entries = [
            make_history_entry(i + 1, 3600, 3600 + (i * 100))  # ~1h est, varying actual
            for i in range(50)
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=3600)
        rng = np.random.default_rng(42)

        sample = sample_jira_duration(dist, context, rng)

        # Should be one of the actual durations from the bin
        assert sample > 0

    def test_sample_no_estimate_uses_all_actuals(self) -> None:
        """When no estimate, samples from all actuals."""
        entries = [
            make_history_entry(1, 3600, 7200),  # 2h
            make_history_entry(2, 7200, 10800),  # 3h
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=None)
        rng = np.random.default_rng(42)

        sample = sample_jira_duration(dist, context, rng)

        # Should be one of the actual durations
        assert sample in [2.0, 3.0]

    def test_sample_no_history_uses_exponential(self) -> None:
        """When no history, uses exponential with mean = estimate."""
        context = JiraSamplingContext(bins=[], all_actuals=[])
        dist = JiraDurationDistribution(original_estimate_seconds=3600)  # 1h
        rng = np.random.default_rng(42)

        # Sample many times to verify distribution
        samples = [sample_jira_duration(dist, context, rng) for _ in range(1000)]

        # Mean should be close to 1.0 (exponential mean = scale)
        mean = np.mean(samples)
        assert 0.7 < mean < 1.3

    def test_sample_no_history_no_estimate_uses_default(self) -> None:
        """When no history and no estimate, uses exponential with 8h mean."""
        context = JiraSamplingContext(bins=[], all_actuals=[])
        dist = JiraDurationDistribution(original_estimate_seconds=None)
        rng = np.random.default_rng(42)

        samples = [sample_jira_duration(dist, context, rng) for _ in range(1000)]

        # Mean should be close to 8.0
        mean = np.mean(samples)
        assert 6.0 < mean < 10.0


class TestSampleJiraDurationFiltered:
    """Tests for sample_jira_duration_filtered."""

    def test_filtered_sampling_returns_valid_sample(self) -> None:
        """Filtered sampling returns values > min_duration."""
        entries = [
            make_history_entry(1, 3600, 3600),  # 1h
            make_history_entry(2, 3600, 7200),  # 2h
            make_history_entry(3, 3600, 14400),  # 4h
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=3600)
        rng = np.random.default_rng(42)

        sample = sample_jira_duration_filtered(dist, context, rng, min_duration=1.5)

        # Should be one of the actuals > 1.5h
        assert sample in [2.0, 4.0]

    def test_filtered_falls_back_to_all_actuals(self) -> None:
        """When bin is exhausted, uses all actuals as fallback."""
        entries = [
            make_history_entry(1, 3600, 3600),  # 1h estimate, 1h actual
            make_history_entry(2, 7200, 14400),  # 2h estimate, 4h actual
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=3600)
        rng = np.random.default_rng(42)

        sample = sample_jira_duration_filtered(dist, context, rng, min_duration=2.0)

        # Only 4h entry is > 2.0
        assert sample == 4.0

    def test_filtered_with_no_estimate_uses_all_actuals(self) -> None:
        """Filtered sampling with no estimate uses all actuals directly."""
        entries = [
            make_history_entry(1, 3600, 3600),  # 1h
            make_history_entry(2, 3600, 7200),  # 2h
            make_history_entry(3, 3600, 14400),  # 4h
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=None)  # No estimate
        rng = np.random.default_rng(42)

        sample = sample_jira_duration_filtered(dist, context, rng, min_duration=1.5)

        # Should be one of the actuals > 1.5h
        assert sample in [2.0, 4.0]

    def test_filtered_exhausted_uses_exponential(self) -> None:
        """When all history exhausted, uses exponential fallback."""
        entries = [
            make_history_entry(1, 3600, 3600),  # 1h
            make_history_entry(2, 3600, 7200),  # 2h
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=3600)
        rng = np.random.default_rng(42)

        sample = sample_jira_duration_filtered(dist, context, rng, min_duration=10.0)

        # Should be >= min_duration
        assert sample >= 10.0

    def test_filtered_deterministic(self) -> None:
        """Filtered sampling is deterministic with seeded RNG."""
        entries = [
            make_history_entry(1, 3600, 7200),
            make_history_entry(2, 3600, 10800),
        ]
        project = make_project_with_history(entries)
        context = build_jira_sampling_context(project)
        dist = JiraDurationDistribution(original_estimate_seconds=3600)

        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)

        sample1 = sample_jira_duration_filtered(dist, context, rng1, min_duration=1.0)
        sample2 = sample_jira_duration_filtered(dist, context, rng2, min_duration=1.0)

        assert sample1 == sample2
