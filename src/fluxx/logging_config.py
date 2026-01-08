"""Logging configuration for Project Fluxx.

This module provides consistent logging setup across all Fluxx components.
"""

import logging
import sys

# Valid log level names (case-insensitive input accepted)
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Default log level
DEFAULT_LOG_LEVEL = "INFO"


def configure_logging(level: str = DEFAULT_LOG_LEVEL) -> None:
    """Configure logging for the application.

    Sets up logging with consistent formatting, outputting to stderr to avoid
    mixing with data output on stdout.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Case-insensitive.

    Raises:
        ValueError: If level is not a valid log level name.
    """
    level_upper = level.upper()

    if level_upper not in LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {level!r}. "
            f"Must be one of: {', '.join(sorted(LOG_LEVELS))}"
        )

    # Get the numeric level
    numeric_level = getattr(logging, level_upper)

    # Configure the root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
        force=True,  # Override any existing configuration
    )
