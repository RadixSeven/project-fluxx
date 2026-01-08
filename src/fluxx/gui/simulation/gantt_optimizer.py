"""Linear programming optimizer for Gantt chart generation.

Solves optimization problem to find conservative Gantt chart schedule per spec 8.1.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from pyomo.environ import (
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    SolverFactory,
    Var,
    minimize,
)

from fluxx.data.models import Endpoint, Project, TaskId
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
    jira_issue_key: str | None = None  # Jira issue key if linked (e.g., "CORE-123")


@dataclass
class GanttSchedule:
    """Optimized Gantt chart schedule."""

    variant_schedules: dict[TaskVariantKey, GanttVariantSchedule]
    optimization_status: str  # "optimal", "infeasible", "error"
    project_start_date: datetime
    world_sequences: set[WorldSequence]
    error_message: str | None = None  # Only set if status != "optimal"


def _compute_parent_schedules(
    variant_schedules: dict[TaskVariantKey, GanttVariantSchedule],
    project: "Project",
    world_sequences: set[WorldSequence],
) -> dict[TaskVariantKey, GanttVariantSchedule]:
    """Compute parent task schedules from optimized children.

    Args:
        variant_schedules: Already optimized leaf task schedules
        project: Project with task hierarchy information
        world_sequences: All world sequences that occurred

    Returns:
        Additional parent task schedules
    """
    from fluxx.gui.simulation.analysis import get_all_tasks_from_project

    # Get all tasks and identify parent tasks
    all_tasks = get_all_tasks_from_project(project)
    parent_tasks = [task for task in all_tasks if task.children]

    parent_schedules: dict[TaskVariantKey, GanttVariantSchedule] = {}

    # For each parent task and world sequence, compute from children
    for parent_task in parent_tasks:
        for world_seq in world_sequences:
            # Find child schedules in this world sequence
            child_schedules = []
            for child_node_id in parent_task.children:
                child_task_id = TaskId(str(child_node_id))
                child_variant_key = TaskVariantKey(child_task_id, world_seq)
                if child_variant_key in variant_schedules:
                    child_schedules.append(variant_schedules[child_variant_key])

            # Only create parent schedule if we have child schedules
            if child_schedules:
                # Parent spans from earliest child start to latest child end
                parent_start = min(sched.start_time for sched in child_schedules)
                parent_end = max(sched.end_time for sched in child_schedules)
                parent_duration_hours = (
                    parent_end - parent_start
                ).total_seconds() / 3600

                # Get Jira issue key if available
                jira_issue_key: str | None = None
                if parent_task.jira_reference is not None:
                    jira_issue_key = str(parent_task.jira_reference.issue_key)

                parent_variant_key = TaskVariantKey(parent_task.id, world_seq)
                parent_schedules[parent_variant_key] = GanttVariantSchedule(
                    variant_key=parent_variant_key,
                    task_title=parent_task.title,
                    start_time=parent_start,
                    duration_hours=parent_duration_hours,
                    end_time=parent_end,
                    jira_issue_key=jira_issue_key,
                )

    return parent_schedules


def optimize_gantt_schedule(
    statistics: GanttStatistics, project: "Project"
) -> GanttSchedule:
    """Solve linear programming problem for conservative Gantt chart.

    Variables (all in calendar hours from project start):
        start[variant]: Start time (calendar hours from project start)
        duration[variant]: Duration (calendar hours)

    Constraints:
        1. start[variant] >= percentile_start_hours[variant]
        2. duration[variant] >= percentile_duration_hours[variant]
        3. Dependency constraints (varies by type and endpoint)

    Objective:
        Minimize: sum(start[variant]) + sum(duration[variant])
        (Both in same unit - calendar hours)

    Args:
        statistics: GanttStatistics with percentile start/duration data
        project: Project with task hierarchy information

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
        ) -> object:
            stats = statistics.task_statistics[variant]
            min_start_hours = (
                stats.percentile_start_time - statistics.project_start_date
            ).total_seconds() / 3600
            return model.start[variant] >= min_start_hours

        def duration_constraint_rule(
            model: ConcreteModel, variant: TaskVariantKey
        ) -> object:
            stats = statistics.task_statistics[variant]
            return model.duration[variant] >= stats.percentile_duration_hours

        model.start_constraints = Constraint(variants, rule=start_constraint_rule)
        model.duration_constraints = Constraint(variants, rule=duration_constraint_rule)

        # Dependency constraints
        # Build map of parent tasks to their children for constraint expansion
        from fluxx.gui.simulation.analysis import get_all_tasks_from_project

        all_tasks = get_all_tasks_from_project(project)
        task_children: dict[TaskId, list[TaskId]] = {}
        for task in all_tasks:
            if task.children:
                task_children[task.id] = [TaskId(str(c)) for c in task.children]

        def get_leaf_descendants(task_id: TaskId) -> list[TaskId]:
            """Get all leaf task descendants of a task (recursive)."""
            children = task_children.get(task_id)
            if not children:
                return [task_id]  # This is a leaf task
            leaves: list[TaskId] = []
            for child_id in children:
                leaves.extend(get_leaf_descendants(child_id))
            return leaves

        # For each dependency in the project, create constraints for all world sequences
        for dep_info in statistics.dependencies:
            source_id = dep_info.source_task_id
            dep = dep_info.dependency
            target_node_id = dep.target_node_id
            target_task_id = TaskId(str(target_node_id))

            # For each world sequence, add dependency constraint if both tasks exist
            for world_seq in statistics.world_sequences:
                source_variant = TaskVariantKey(source_id, world_seq)

                # Skip if source doesn't exist in this world sequence
                if source_variant not in variants:
                    continue

                # Check if target is a leaf task or parent task
                target_variant = TaskVariantKey(target_task_id, world_seq)
                if target_variant in variants:
                    # Target is a leaf task - use directly
                    target_variants_to_use = [target_variant]
                elif dep.target_endpoint == Endpoint.END:
                    # Target is a parent task with END endpoint - expand to children
                    # parent.end = max(child.end), so X >= parent.end means
                    # X >= child1.end AND X >= child2.end AND ...
                    leaf_task_ids = get_leaf_descendants(target_task_id)
                    target_variants_to_use = [
                        TaskVariantKey(leaf_id, world_seq)
                        for leaf_id in leaf_task_ids
                        if TaskVariantKey(leaf_id, world_seq) in variants
                    ]
                else:
                    # Target is a parent task with START endpoint
                    # parent.start = min(child.start) - can't expand meaningfully
                    # For child.start >= parent.start where child is in parent,
                    # this is always satisfied by definition. Skip this constraint.
                    continue

                # Skip if no valid targets found
                if not target_variants_to_use:
                    continue

                # Add constraint for each target variant
                for idx, target_variant in enumerate(target_variants_to_use):
                    # Unique constraint name includes index for expanded parent deps
                    constraint_name = (
                        f"dep_{source_id}_{target_variant.task_id}_{world_seq}_{idx}"
                    )

                    # Build constraint based on source/target endpoints
                    # Source is always the task with the dependency
                    # Target is what it depends on
                    if (
                        dep.source_endpoint == Endpoint.START
                        and dep.target_endpoint == Endpoint.END
                    ):
                        # B.start >= A.end  =>  start[B] >= start[A] + duration[A]
                        model.add_component(
                            constraint_name,
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
                            constraint_name,
                            Constraint(
                                expr=model.start[source_variant]
                                >= model.start[target_variant]
                            ),
                        )
                    elif (
                        dep.source_endpoint == Endpoint.END
                        and dep.target_endpoint == Endpoint.END
                    ):
                        # B.end >= A.end => start[B]+duration[B] >= start[A]+duration[A]
                        model.add_component(
                            constraint_name,
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
                            constraint_name,
                            Constraint(
                                expr=model.start[source_variant]
                                + model.duration[source_variant]
                                >= model.start[target_variant]
                            ),
                        )

        # Objective: minimize sum of starts and durations (both in calendar hours)
        def objective_rule(model: ConcreteModel) -> object:
            return sum(model.start[v] for v in variants) + sum(
                model.duration[v] for v in variants
            )

        model.obj = Objective(rule=objective_rule, sense=minimize)

        # Solve with appsi_highs (Pyomo interface to HiGHS solver)
        solver = SolverFactory("appsi_highs")
        results = solver.solve(model)

        # Check solver status
        from pyomo.opt import (
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

                task_stats = statistics.task_statistics[variant]
                task_title = task_stats.task_title
                jira_issue_key = task_stats.jira_issue_key

                variant_schedules[variant] = GanttVariantSchedule(
                    variant_key=variant,
                    task_title=task_title,
                    start_time=start_time,
                    duration_hours=duration_hours,
                    end_time=end_time,
                    jira_issue_key=jira_issue_key,
                )

            # Compute parent task schedules from optimized children
            parent_schedules = _compute_parent_schedules(
                variant_schedules, project, statistics.world_sequences
            )
            # Merge parent schedules into variant_schedules
            variant_schedules.update(parent_schedules)

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
