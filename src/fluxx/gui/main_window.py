"""Main window for Project Fluxx application."""

from PyQt6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    """Main application window for Project Fluxx."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Project Fluxx")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget with placeholder content
        central_widget = QWidget()
        layout = QVBoxLayout()

        label = QLabel("Project Fluxx - Coming Soon")
        label.setStyleSheet("font-size: 24px; padding: 50px;")
        layout.addWidget(label)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
