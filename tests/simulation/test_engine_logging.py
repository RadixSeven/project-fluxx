"""Tests for simulation engine logging."""

import logging
from datetime import UTC, datetime

import numpy as np
import pytest

from fluxx.data.models import (
    DAG,
    DAGId,
    DAGVersionId,
    PersistentObjectId,
    PersistentTask,
    Project,
    ProjectMetadata,
    Task,
    TaskId,
    Triangular,
    Worker,
    WorkerId,
)
from fluxx.simulation.engine import SimulationEngine, run_single_sample


def create_simple_project() -> Project:
    """Create a simple project with one task for testing."""
    version_id = DAGVersionId("v1")
    task_id = TaskId("task-1")
    persistent_id = PersistentObjectId("pt-1")

    task = Task(
        id=task_id,
        title="Test Task",
        description="A test task",
        duration_distribution=Triangular(min=1.0, mode=2.0, max=4.0),
    )

    persistent_task = PersistentTask(
        id=persistent_id,
        versions={version_id: task},
    )

    dag = DAG(
        id=DAGId("dag-1"),
        current_version_id=version_id,
        node_map={task_id: persistent_id},
    )

    metadata = ProjectMetadata(
        name="Test Project",
        created=datetime(2025, 1, 1, tzinfo=UTC),
        last_modified=datetime(2025, 1, 1, tzinfo=UTC),
    )

    return Project(
        metadata=metadata,
        dag=dag,
        persistent_tasks={persistent_id: persistent_task},
    )


def create_workers() -> list[Worker]:
    """Create a simple worker list for testing."""
    return [Worker(id=WorkerId("worker-1"), name="Test Worker", hours_per_workday=8.0)]


class TestSimulationEngineLogging:
    """Tests for SimulationEngine logging."""

    def test_simulation_logs_start_at_info_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that simulation start is logged at INFO level."""
        project = create_simple_project()
        workers = create_workers()

        engine = SimulationEngine(num_samples=5)

        with caplog.at_level(logging.INFO, logger="fluxx.simulation.engine"):
            engine.run(project, workers)

        # Check for simulation start message
        assert any("Simulation starting" in record.message for record in caplog.records)

    def test_simulation_logs_completion_at_info_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that simulation completion is logged at INFO level."""
        project = create_simple_project()
        workers = create_workers()

        engine = SimulationEngine(num_samples=5)

        with caplog.at_level(logging.INFO, logger="fluxx.simulation.engine"):
            engine.run(project, workers)

        # Check for simulation complete message
        assert any("Simulation complete" in record.message for record in caplog.records)

    def test_simulation_logs_sample_count(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that simulation logs the number of samples."""
        project = create_simple_project()
        workers = create_workers()

        engine = SimulationEngine(num_samples=10)

        with caplog.at_level(logging.INFO, logger="fluxx.simulation.engine"):
            engine.run(project, workers)

        # Check that num_samples=10 appears in a log message
        assert any("num_samples=10" in record.message for record in caplog.records)

    def test_simulation_logs_elapsed_time(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that simulation logs elapsed time."""
        project = create_simple_project()
        workers = create_workers()

        engine = SimulationEngine(num_samples=5)

        with caplog.at_level(logging.INFO, logger="fluxx.simulation.engine"):
            engine.run(project, workers)

        # Check that elapsed time appears in a log message
        assert any("elapsed=" in record.message for record in caplog.records)

    def test_sample_start_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that sample start is logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.engine"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for sample starting message
        assert any("Sample 0 starting" in record.message for record in caplog.records)

    def test_sample_completion_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that sample completion is logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.engine"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for sample completion message
        assert any(
            "Sample 0 completed successfully" in record.message
            for record in caplog.records
        )

    def test_task_start_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that task start is logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.engine"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for task start message
        assert any("Task task-1 started" in record.message for record in caplog.records)

    def test_task_completion_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that task completion is logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.engine"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for task completion message
        assert any(
            "Task task-1 completed" in record.message for record in caplog.records
        )


class TestSchedulerLogging:
    """Tests for scheduler logging."""

    def test_scheduling_step_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that scheduling steps are logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.scheduler"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for scheduling step message
        assert any("Scheduling step" in record.message for record in caplog.records)

    def test_selected_action_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that selected actions are logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.scheduler"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for selected action message
        assert any("Selected action" in record.message for record in caplog.records)


class TestStateLogging:
    """Tests for simulation state logging."""

    def test_worker_busy_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that worker becoming busy is logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.state"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for worker busy message
        assert any(
            "Worker worker-1 now busy" in record.message for record in caplog.records
        )

    def test_worker_idle_logged_at_debug_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that worker becoming idle is logged at DEBUG level."""
        project = create_simple_project()
        workers = create_workers()
        rng = np.random.default_rng(seed=42)

        with caplog.at_level(logging.DEBUG, logger="fluxx.simulation.state"):
            run_single_sample(
                project,
                workers,
                datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                sample_id=0,
                rng=rng,
            )

        # Check for worker idle message
        assert any(
            "Worker worker-1 now idle" in record.message for record in caplog.records
        )
