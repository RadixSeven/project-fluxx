"""Linear programming optimizer for Gantt chart generation.

Solves optimization problem to find conservative Gantt chart schedule per spec 8.1.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from pyomo.environ import (  # type: ignore[import-untyped]
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    SolverFactory,
    Var,
    minimize,
)

from fluxx.data.models import Endpoint, TaskId
from fluxx.gui.simulation.gantt_analysis import (
    GanttStatistics,
    TaskVariantKey,
    WorldSequence,
)


@dataclass
class GanttVariantSchedule:
    """Schedule for a single task variant."""

    variant_key: TaskVariantKey
    task_title: str
    start_time: datetime  # Absolute calendar time
    duration_hours: float  # Duration in calendar hours
    end_time: datetime  # Computed from start + duration


@dataclass
class GanttSchedule:
    """Optimized Gantt chart schedule."""

    variant_schedules: dict[TaskVariantKey, GanttVariantSchedule]
    optimization_status: str  # "optimal", "infeasible", "error"
    project_start_date: datetime
    world_sequences: set[WorldSequence]
    error_message: str | None = None  # Only set if status != "optimal"


def optimize_gantt_schedule(statistics: GanttStatistics) -> GanttSchedule:
    """Solve linear programming problem for conservative Gantt chart.

    Variables (all in calendar hours from project start):
        start[variant]: Start time (calendar hours from project start)
        duration[variant]: Duration (calendar hours)

    Constraints:
        1. start[variant] >= percentile_start_hours[variant]
        2. duration[variant] >= percentile_duration_hours[variant]
        3. Dependency constraints (varies by type and endpoint)
        4. Parent task constraints (children determine parent bounds)

    Objective:
        Minimize: sum(start[variant]) + sum(duration[variant])
        (Both in same unit - calendar hours)

    Args:
        statistics: GanttStatistics with percentile start/duration data

    Returns:
        GanttSchedule with optimized start times and durations
    """
    try:
        # Get list of all task variants
        variants = list(statistics.task_statistics.keys())

        # Handle empty case
        if not variants:
            return GanttSchedule(
                variant_schedules={},
                optimization_status="optimal",
                project_start_date=statistics.project_start_date,
                world_sequences=statistics.world_sequences,
            )

        model = ConcreteModel()

        # Decision variables (all in calendar hours from project start)
        model.start = Var(variants, domain=NonNegativeReals)
        model.duration = Var(variants, domain=NonNegativeReals)

        # Percentile constraints
        def start_constraint_rule(
            model: ConcreteModel, variant: TaskVariantKey
        ) -> bool:
            stats = statistics.task_statistics[variant]
            min_start_hours = (
                stats.percentile_start_time - statistics.project_start_date
            ).total_seconds() / 3600
            return model.start[variant] >= min_start_hours  # type: ignore[no-any-return]

        def duration_constraint_rule(
            model: ConcreteModel, variant: TaskVariantKey
        ) -> bool:
            stats = statistics.task_statistics[variant]
            return model.duration[variant] >= stats.percentile_duration_hours  # type: ignore[no-any-return]

        model.start_constraints = Constraint(variants, rule=start_constraint_rule)
        model.duration_constraints = Constraint(variants, rule=duration_constraint_rule)

        # Dependency constraints
        # For each dependency in the project, create constraints for all world sequences
        for dep_info in statistics.dependencies:
            source_id = dep_info.source_task_id
            dep = dep_info.dependency
            target_node_id = dep.target_node_id

            # For each world sequence, add dependency constraint if both tasks exist
            for world_seq in statistics.world_sequences:
                source_variant = TaskVariantKey(source_id, world_seq)
                target_variant = TaskVariantKey(TaskId(str(target_node_id)), world_seq)

                # Skip if either variant doesn't exist in this world sequence
                if source_variant not in variants or target_variant not in variants:
                    continue

                # Build constraint based on source/target endpoints
                # Source is always the task with the dependency
                # Target is what it depends on
                if (
                    dep.source_endpoint == Endpoint.START
                    and dep.target_endpoint == Endpoint.END
                ):
                    # B.start >= A.end  =>  start[B] >= start[A] + duration[A]
                    model.add_component(
                        f"dep_{source_id}_{target_node_id}_{world_seq}",
                        Constraint(
                            expr=model.start[source_variant]
                            >= model.start[target_variant]
                            + model.duration[target_variant]
                        ),
                    )
                elif (
                    dep.source_endpoint == Endpoint.START
                    and dep.target_endpoint == Endpoint.START
                ):
                    # B.start >= A.start  =>  start[B] >= start[A]
                    model.add_component(
                        f"dep_{source_id}_{target_node_id}_{world_seq}",
                        Constraint(
                            expr=model.start[source_variant]
                            >= model.start[target_variant]
                        ),
                    )
                elif (
                    dep.source_endpoint == Endpoint.END
                    and dep.target_endpoint == Endpoint.END
                ):
                    # B.end >= A.end => start[B] + duration[B] >= start[A] + duration[A]
                    model.add_component(
                        f"dep_{source_id}_{target_node_id}_{world_seq}",
                        Constraint(
                            expr=model.start[source_variant]
                            + model.duration[source_variant]
                            >= model.start[target_variant]
                            + model.duration[target_variant]
                        ),
                    )
                elif (
                    dep.source_endpoint == Endpoint.END
                    and dep.target_endpoint == Endpoint.START
                ):
                    # B.end >= A.start  =>  start[B] + duration[B] >= start[A]
                    model.add_component(
                        f"dep_{source_id}_{target_node_id}_{world_seq}",
                        Constraint(
                            expr=model.start[source_variant]
                            + model.duration[source_variant]
                            >= model.start[target_variant]
                        ),
                    )

        # Objective: minimize sum of starts and durations (both in calendar hours)
        def objective_rule(model: ConcreteModel) -> float:
            return sum(model.start[v] for v in variants) + sum(  # type: ignore[no-any-return]
                model.duration[v] for v in variants
            )

        model.obj = Objective(rule=objective_rule, sense=minimize)

        # Solve with appsi_highs (Pyomo interface to HiGHS solver)
        solver = SolverFactory("appsi_highs")
        results = solver.solve(model)

        # Check solver status
        from pyomo.opt import (  # type: ignore[import-untyped]
            SolverStatus,
            TerminationCondition,
        )

        if (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        ):
            # Convert solution to GanttSchedule
            variant_schedules = {}
            for variant in variants:
                start_hours = model.start[variant].value
                duration_hours = model.duration[variant].value

                # Convert to datetime
                start_time = statistics.project_start_date + timedelta(
                    hours=start_hours
                )
                end_time = start_time + timedelta(hours=duration_hours)

                task_title = statistics.task_statistics[variant].task_title

                variant_schedules[variant] = GanttVariantSchedule(
                    variant_key=variant,
                    task_title=task_title,
                    start_time=start_time,
                    duration_hours=duration_hours,
                    end_time=end_time,
                )

            return GanttSchedule(
                variant_schedules=variant_schedules,
                optimization_status="optimal",
                project_start_date=statistics.project_start_date,
                world_sequences=statistics.world_sequences,
            )

        elif results.solver.termination_condition == TerminationCondition.infeasible:
            # Infeasible problem
            return GanttSchedule(
                variant_schedules={},
                optimization_status="infeasible",
                project_start_date=statistics.project_start_date,
                world_sequences=statistics.world_sequences,
                error_message=(
                    "Optimization problem is infeasible. "
                    "This may indicate conflicting dependencies "
                    "or impossible constraints."
                ),
            )

        else:
            # Other solver error
            return GanttSchedule(
                variant_schedules={},
                optimization_status="error",
                project_start_date=statistics.project_start_date,
                world_sequences=statistics.world_sequences,
                error_message=f"Solver error: {results.solver.termination_condition}",
            )

    except Exception as e:
        # Catch any other errors (e.g., solver not found)
        error_msg = str(e)
        if "highs" in error_msg.lower() or "solver" in error_msg.lower():
            error_msg = (
                "HiGHS solver not found. "
                "Please ensure dependencies are installed: pip install -e ."
            )

        return GanttSchedule(
            variant_schedules={},
            optimization_status="error",
            project_start_date=statistics.project_start_date,
            world_sequences=statistics.world_sequences,
            error_message=error_msg,
        )
