"""Test that Task.allowed_workers normalizes empty lists to None."""

from fluxx.data.models import Task, TaskId, Triangular, WorkerId


def test_allowed_workers_none_stays_none() -> None:
    """Test that None remains None."""
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=None,
    )

    assert task.allowed_workers is None


def test_allowed_workers_empty_list_normalized_to_none() -> None:
    """Test that empty list is normalized to None."""
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[],
    )

    # Empty list should be normalized to None
    assert task.allowed_workers is None


def test_allowed_workers_with_values_unchanged() -> None:
    """Test that non-empty list is preserved."""
    workers = [WorkerId("w1"), WorkerId("w2")]
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=workers,
    )

    assert task.allowed_workers == workers
    assert task.allowed_workers is not None
    assert len(task.allowed_workers) == 2


def test_get_allowed_worker_ids_with_none() -> None:
    """Test get_allowed_worker_ids returns all workers when None."""
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=None,
    )

    all_workers = [WorkerId("w1"), WorkerId("w2"), WorkerId("w3")]
    result = task.get_allowed_worker_ids(all_workers)

    assert result == all_workers


def test_get_allowed_worker_ids_with_empty_list_normalized() -> None:
    """Test get_allowed_worker_ids returns all workers when empty list.

    Empty list is normalized to None by the validator.
    """
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=[],  # Will be normalized to None
    )

    all_workers = [WorkerId("w1"), WorkerId("w2"), WorkerId("w3")]
    result = task.get_allowed_worker_ids(all_workers)

    # Should return all workers since empty list was normalized to None
    assert result == all_workers


def test_get_allowed_worker_ids_with_whitelist() -> None:
    """Test get_allowed_worker_ids returns whitelist when specified."""
    whitelist = [WorkerId("w1"), WorkerId("w2")]
    task = Task(
        id=TaskId("t1"),
        title="Test Task",
        description="",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=3.0),
        allowed_workers=whitelist,
    )

    all_workers = [WorkerId("w1"), WorkerId("w2"), WorkerId("w3")]
    result = task.get_allowed_worker_ids(all_workers)

    # Should return only the whitelist
    assert result == whitelist
    assert WorkerId("w3") not in result
