"""Type stubs for matplotlib.backends.backend_qtagg module.

These stubs provide type information for the Qt backend classes used in the project.
"""

from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget

class FigureCanvasQTAgg(QWidget):
    """Canvas for rendering matplotlib figures in Qt applications."""

    def __init__(self, figure: Figure) -> None: ...
    def draw(self) -> None: ...

class NavigationToolbar2QT(QWidget):
    """Navigation toolbar for matplotlib figures in Qt applications."""

    def __init__(self, canvas: FigureCanvasQTAgg, parent: QWidget) -> None: ...
