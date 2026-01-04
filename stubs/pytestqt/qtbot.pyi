"""Type stubs for pytestqt.qtbot module.

These stubs provide type information for the QtBot test fixture.
"""

from types import TracebackType

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QWidget

class _SignalBlocker:
    """Context manager returned by waitSignal/waitSignals."""

    def __enter__(self) -> _SignalBlocker: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

class QtBot:
    """QtBot fixture for pytest-qt testing."""

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        """Register a widget for cleanup after the test."""
        ...

    def mouseClick(  # noqa: N802
        self,
        widget: QWidget,
        button: Qt.MouseButton,
        modifier: Qt.KeyboardModifier = ...,
        pos: QPoint = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a mouse click on a widget."""
        ...

    def mousePress(  # noqa: N802
        self,
        widget: QWidget,
        button: Qt.MouseButton,
        modifier: Qt.KeyboardModifier = ...,
        pos: QPoint = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a mouse press on a widget."""
        ...

    def mouseRelease(  # noqa: N802
        self,
        widget: QWidget,
        button: Qt.MouseButton,
        modifier: Qt.KeyboardModifier = ...,
        pos: QPoint = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a mouse release on a widget."""
        ...

    def mouseMove(  # noqa: N802
        self,
        widget: QWidget,
        pos: QPoint = ...,
        delay: int = ...,
    ) -> None:
        """Simulate mouse movement."""
        ...

    def mouseDClick(  # noqa: N802
        self,
        widget: QWidget,
        button: Qt.MouseButton,
        modifier: Qt.KeyboardModifier = ...,
        pos: QPoint = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a mouse double-click on a widget."""
        ...

    def keyClick(  # noqa: N802
        self,
        widget: QWidget,
        key: Qt.Key | str,
        modifier: Qt.KeyboardModifier = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a key click on a widget."""
        ...

    def keyClicks(  # noqa: N802
        self,
        widget: QWidget,
        sequence: str,
        modifier: Qt.KeyboardModifier = ...,
        delay: int = ...,
    ) -> None:
        """Simulate multiple key clicks on a widget."""
        ...

    def keyPress(  # noqa: N802
        self,
        widget: QWidget,
        key: Qt.Key | str,
        modifier: Qt.KeyboardModifier = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a key press on a widget."""
        ...

    def keyRelease(  # noqa: N802
        self,
        widget: QWidget,
        key: Qt.Key | str,
        modifier: Qt.KeyboardModifier = ...,
        delay: int = ...,
    ) -> None:
        """Simulate a key release on a widget."""
        ...

    def wait(self, ms: int) -> None:
        """Wait for the given number of milliseconds."""
        ...

    def waitUntil(  # noqa: N802
        self,
        callback: object,
        timeout: int = ...,
    ) -> None:
        """Wait until the callback returns True."""
        ...

    def waitExposed(  # noqa: N802
        self,
        widget: QWidget,
        timeout: int = ...,
    ) -> None:
        """Wait until the widget is exposed."""
        ...

    def waitSignal(  # noqa: N802
        self,
        signal: object,
        timeout: int = ...,
        raising: bool = ...,
    ) -> _SignalBlocker:
        """Wait for a signal to be emitted.

        Returns a context manager that can be used with a 'with' statement.
        """
        ...

    def waitSignals(  # noqa: N802
        self,
        signals: list[object],
        timeout: int = ...,
        raising: bool = ...,
    ) -> _SignalBlocker:
        """Wait for multiple signals to be emitted.

        Returns a context manager that can be used with a 'with' statement.
        """
        ...
