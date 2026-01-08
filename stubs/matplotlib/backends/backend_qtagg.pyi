"""Type stubs for matplotlib.backends.backend_qtagg module.

These stubs provide type information for the Qt backend classes used in the project.
"""

from collections.abc import Callable

from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget

class CallbackRegistry:
    """Registry for managing callbacks."""

    def process(self, event: str, *args: object, **kwargs: object) -> None: ...

class FigureCanvasQTAgg(QWidget):
    """Canvas for rendering matplotlib figures in Qt applications."""

    callbacks: CallbackRegistry

    def __init__(self, figure: Figure) -> None: ...
    def draw(self) -> None: ...
    def draw_idle(self) -> None: ...
    def mpl_connect(self, event: str, callback: Callable[[object], None]) -> int: ...

class NavigationToolbar2QT(QWidget):
    """Navigation toolbar for matplotlib figures in Qt applications."""

    def __init__(self, canvas: FigureCanvasQTAgg, parent: QWidget) -> None: ...
