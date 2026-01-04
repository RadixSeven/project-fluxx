"""Type stubs for pyomo.environ module.

These stubs provide type information for the Pyomo optimization modeling classes.
"""

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

_T = TypeVar("_T")

# Type alias for numeric operands in Pyomo expressions
type _Numeric = float | int
type _ExpressionLike = "Expression | _Numeric"

class ConcreteModel:
    """A concrete Pyomo optimization model.

    Note: Pyomo models support dynamic attribute assignment for variables,
    constraints, and objectives. We use __setattr__ and __getattr__ to allow this.
    """

    def __init__(self) -> None: ...
    def add_component(self, name: str, component: object) -> None: ...
    def __setattr__(self, name: str, value: object) -> None: ...
    def __getattr__(self, name: str) -> Any: ...

class Expression:
    """Pyomo expression type for arithmetic operations.

    Expressions are the result of arithmetic operations on Pyomo variables.
    They are used as constraint bodies and objective functions.
    """

    def __add__(self, other: _ExpressionLike) -> Expression: ...
    def __radd__(self, other: _ExpressionLike) -> Expression: ...
    def __sub__(self, other: _ExpressionLike) -> Expression: ...
    def __rsub__(self, other: _ExpressionLike) -> Expression: ...
    def __mul__(self, other: _ExpressionLike) -> Expression: ...
    def __rmul__(self, other: _ExpressionLike) -> Expression: ...
    def __truediv__(self, other: _ExpressionLike) -> Expression: ...
    def __ge__(self, other: _ExpressionLike) -> Expression: ...
    def __le__(self, other: _ExpressionLike) -> Expression: ...
    def __eq__(self, other: _ExpressionLike) -> Expression: ...  # type: ignore[override]

class Var(Expression):
    """A Pyomo decision variable."""

    value: float

    def __init__(
        self,
        *indexes: Iterable[object],
        domain: object = ...,
        bounds: tuple[float, float] | None = ...,
        initialize: float | None = ...,
    ) -> None: ...
    def __getitem__(self, key: object) -> Var: ...

class Constraint:
    """A Pyomo constraint."""

    def __init__(
        self,
        *indexes: object,
        rule: Callable[..., object] | None = ...,
        expr: object = ...,
    ) -> None: ...

class Objective:
    """A Pyomo objective function."""

    def __init__(
        self,
        *indexes: object,
        rule: Callable[..., object] | None = ...,
        expr: object = ...,
        sense: object = ...,
    ) -> None: ...

class Domain:
    """Base class for variable domains."""

NonNegativeReals: Domain

def minimize() -> object:
    """Minimize sense for objectives."""
    ...

class SolverFactory:
    """Factory for creating optimization solvers."""

    def __init__(self, solver_name: str) -> None: ...
    def solve(self, model: ConcreteModel) -> SolverResults: ...

class SolverResults:
    """Results from solving an optimization problem."""

    solver: SolverInfo

class SolverInfo:
    """Information about the solver run."""

    status: object
    termination_condition: object
