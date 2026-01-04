"""Type stubs for matplotlib.dates module.

These stubs provide type information for matplotlib.dates functions and classes
used in the project. The official matplotlib package is typed but missing
stubs for the dates module.
"""

from collections.abc import Sequence
from datetime import datetime

from matplotlib.ticker import Formatter, Locator

# The true type stub is:
# def date2num(d: datetime | Sequence[datetime]) -> float | Sequence[float]: ...
# but we only use the single item version and the code is simpler if we don't
# need to narrow the output.
def date2num(d: datetime) -> float: ...
def num2date(x: float) -> datetime: ...

class DateFormatter(Formatter):
    def __init__(
        self, fmt: str, tz: str | None = None, *, usetex: bool | None = None
    ) -> None: ...

class AutoDateLocator(Locator):
    def __init__(
        self,
        tz: str | None = None,
        minticks: int = 5,
        maxticks: int | None = None,
        interval_multiples: bool = True,
    ) -> None: ...

class DayLocator(Locator):
    def __init__(
        self,
        bymonthday: int | Sequence[int] | None = None,
        interval: int = 1,
        tz: str | None = None,
    ) -> None: ...

class WeekdayLocator(Locator):
    def __init__(
        self,
        byweekday: int | Sequence[int] = 0,
        interval: int = 1,
        tz: str | None = None,
    ) -> None: ...

class MonthLocator(Locator):
    def __init__(
        self,
        bymonth: int | Sequence[int] | None = None,
        bymonthday: int = 1,
        interval: int = 1,
        tz: str | None = None,
    ) -> None: ...
