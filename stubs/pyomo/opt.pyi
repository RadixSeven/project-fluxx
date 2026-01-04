"""Type stubs for pyomo.opt module.

These stubs provide type information for Pyomo solver status classes.
"""

from enum import Enum

class SolverStatus(Enum):
    """Status of a solver run."""

    ok = "ok"
    warning = "warning"
    error = "error"
    aborted = "aborted"
    unknown = "unknown"

class TerminationCondition(Enum):
    """Termination condition of a solver run."""

    optimal = "optimal"
    infeasible = "infeasible"
    unbounded = "unbounded"
    maxIterations = "maxIterations"  # noqa: N815
    maxTimeLimit = "maxTimeLimit"  # noqa: N815
    other = "other"
    unknown = "unknown"
