"""Tests for logging configuration module."""

import logging
import sys
from io import StringIO

import pytest

from fluxx.logging_config import (
    DEFAULT_LOG_LEVEL,
    LOG_LEVELS,
    configure_logging,
)


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_default_level_is_info(self) -> None:
        """Test that default log level is INFO."""
        assert DEFAULT_LOG_LEVEL == "INFO"

    def test_log_levels_are_valid(self) -> None:
        """Test that LOG_LEVELS contains all standard levels."""
        expected = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        assert expected == LOG_LEVELS

    def test_configure_sets_level_debug(self) -> None:
        """Test configure_logging sets DEBUG level."""
        configure_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_configure_sets_level_info(self) -> None:
        """Test configure_logging sets INFO level."""
        configure_logging("INFO")
        assert logging.getLogger().level == logging.INFO

    def test_configure_sets_level_warning(self) -> None:
        """Test configure_logging sets WARNING level."""
        configure_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_configure_sets_level_error(self) -> None:
        """Test configure_logging sets ERROR level."""
        configure_logging("ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_configure_sets_level_critical(self) -> None:
        """Test configure_logging sets CRITICAL level."""
        configure_logging("CRITICAL")
        assert logging.getLogger().level == logging.CRITICAL

    def test_case_insensitivity_lowercase(self) -> None:
        """Test that log level is case-insensitive (lowercase)."""
        configure_logging("debug")
        assert logging.getLogger().level == logging.DEBUG

    def test_case_insensitivity_mixed_case(self) -> None:
        """Test that log level is case-insensitive (mixed case)."""
        configure_logging("DeBuG")
        assert logging.getLogger().level == logging.DEBUG

    def test_invalid_level_raises_value_error(self) -> None:
        """Test that invalid log level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid log level"):
            configure_logging("INVALID")

    def test_invalid_level_error_message_contains_level(self) -> None:
        """Test that error message contains the invalid level."""
        with pytest.raises(ValueError, match="'INVALID'"):
            configure_logging("INVALID")

    def test_output_goes_to_stderr(self) -> None:
        """Test that log output goes to stderr."""
        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            configure_logging("DEBUG")
            logger = logging.getLogger("test_stderr")
            logger.debug("test message")

            output = sys.stderr.getvalue()
            assert "test message" in output
        finally:
            sys.stderr = old_stderr

    def test_log_format_contains_expected_parts(self) -> None:
        """Test that log format contains expected components."""
        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            configure_logging("DEBUG")
            logger = logging.getLogger("test_format")
            logger.debug("format test")

            output = sys.stderr.getvalue()
            # Check format components: timestamp, level, logger name, message
            assert "DEBUG" in output
            assert "[test_format]" in output
            assert "format test" in output
        finally:
            sys.stderr = old_stderr

    def test_reconfigure_changes_level(self) -> None:
        """Test that calling configure_logging again changes the level."""
        configure_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

        configure_logging("ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_default_parameter(self) -> None:
        """Test configure_logging with no arguments uses default level."""
        configure_logging()
        assert logging.getLogger().level == logging.INFO
