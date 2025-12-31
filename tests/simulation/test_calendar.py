"""Tests for calendar and work-time utilities."""

from datetime import UTC, datetime

from fluxx.simulation.calendar import (
    WorkCalendar,
    add_work_hours,
    calculate_work_hours_between,
    is_weekend,
    skip_to_monday,
    start_of_next_workday,
)


def test_is_weekend() -> None:
    """Test weekend detection."""
    # Monday (weekday 0)
    monday = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)  # This is a Monday
    assert not is_weekend(monday)

    # Friday (weekday 4)
    friday = datetime(2024, 1, 5, 9, 0, 0, tzinfo=UTC)
    assert not is_weekend(friday)

    # Saturday (weekday 5)
    saturday = datetime(2024, 1, 6, 9, 0, 0, tzinfo=UTC)
    assert is_weekend(saturday)

    # Sunday (weekday 6)
    sunday = datetime(2024, 1, 7, 9, 0, 0, tzinfo=UTC)
    assert is_weekend(sunday)


def test_skip_to_monday() -> None:
    """Test skipping from weekend to Monday."""
    # Saturday at 10 AM should skip to Monday at 10 AM
    saturday = datetime(2024, 1, 6, 10, 0, 0, tzinfo=UTC)
    monday = skip_to_monday(saturday)
    assert monday == datetime(2024, 1, 8, 10, 0, 0, tzinfo=UTC)
    assert not is_weekend(monday)

    # Sunday at 2 PM should skip to Monday at 2 PM
    sunday = datetime(2024, 1, 7, 14, 0, 0, tzinfo=UTC)
    monday = skip_to_monday(sunday)
    assert monday == datetime(2024, 1, 8, 14, 0, 0, tzinfo=UTC)
    assert not is_weekend(monday)

    # Monday should return unchanged
    monday_in = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    monday_out = skip_to_monday(monday_in)
    assert monday_out == monday_in


def test_start_of_next_workday() -> None:
    """Test moving to start of next workday."""
    # Wednesday afternoon -> Thursday 9 AM
    wednesday = datetime(2024, 1, 3, 15, 30, 0, tzinfo=UTC)
    thursday = start_of_next_workday(wednesday)
    assert thursday == datetime(2024, 1, 4, 9, 0, 0, tzinfo=UTC)

    # Friday afternoon -> Monday 9 AM (skip weekend)
    friday = datetime(2024, 1, 5, 17, 0, 0, tzinfo=UTC)
    monday = start_of_next_workday(friday)
    assert monday == datetime(2024, 1, 8, 9, 0, 0, tzinfo=UTC)

    # Saturday -> Monday 9 AM
    saturday = datetime(2024, 1, 6, 12, 0, 0, tzinfo=UTC)
    monday = start_of_next_workday(saturday)
    assert monday == datetime(2024, 1, 8, 9, 0, 0, tzinfo=UTC)


def test_add_work_hours_within_same_day() -> None:
    """Test adding work hours within the same workday."""
    # Monday 9 AM + 4 hours = Monday 1 PM
    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    end = add_work_hours(start, 4.0, 8.0)
    assert end == datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)


def test_add_work_hours_across_days() -> None:
    """Test adding work hours that span multiple days."""
    # Monday 9 AM + 10 hours (with 8 hour days) = Tuesday 11 AM
    # Day 1: 8 hours (9 AM to 5 PM)
    # Day 2: 2 hours (9 AM to 11 AM)
    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    end = add_work_hours(start, 10.0, 8.0)
    assert end == datetime(2024, 1, 2, 11, 0, 0, tzinfo=UTC)


def test_add_work_hours_across_weekend() -> None:
    """Test adding work hours that cross a weekend."""
    # Friday 9 AM + 10 hours (with 8 hour days) = Monday 11 AM
    # Friday: 8 hours (9 AM to 5 PM)
    # Weekend: skipped
    # Monday: 2 hours (9 AM to 11 AM)
    friday = datetime(2024, 1, 5, 9, 0, 0, tzinfo=UTC)
    monday = add_work_hours(friday, 10.0, 8.0)
    assert monday == datetime(2024, 1, 8, 11, 0, 0, tzinfo=UTC)


def test_add_work_hours_starting_on_weekend() -> None:
    """Test adding work hours when starting on a weekend."""
    # Saturday 10 AM skips to Monday 10 AM, then + 4 hours = Monday 2 PM
    saturday = datetime(2024, 1, 6, 10, 0, 0, tzinfo=UTC)
    monday = add_work_hours(saturday, 4.0, 8.0)
    assert monday == datetime(2024, 1, 8, 14, 0, 0, tzinfo=UTC)


def test_add_work_hours_mid_day() -> None:
    """Test adding work hours starting mid-day."""
    # Monday 2 PM + 6 hours (with 8 hour days) = Tuesday 12 PM
    # Monday: 3 hours remaining (2 PM to 5 PM)
    # Tuesday: 3 hours (9 AM to 12 PM)
    monday = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)
    tuesday = add_work_hours(monday, 6.0, 8.0)
    assert tuesday == datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC)


def test_add_zero_hours() -> None:
    """Test adding zero work hours."""
    start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = add_work_hours(start, 0.0, 8.0)
    assert end == start


def test_calculate_work_hours_same_day() -> None:
    """Test calculating work hours within same day."""
    # Monday 9 AM to Monday 1 PM = 4 hours
    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
    hours = calculate_work_hours_between(start, end, 8.0)
    assert abs(hours - 4.0) < 0.01


def test_calculate_work_hours_across_days() -> None:
    """Test calculating work hours across multiple days."""
    # Monday 9 AM to Tuesday 11 AM = 10 hours
    # Monday: 8 hours (9 AM to 5 PM)
    # Tuesday: 2 hours (9 AM to 11 AM)
    start = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 2, 11, 0, 0, tzinfo=UTC)
    hours = calculate_work_hours_between(start, end, 8.0)
    assert abs(hours - 10.0) < 0.01


def test_calculate_work_hours_across_weekend() -> None:
    """Test calculating work hours across a weekend."""
    # Friday 9 AM to Monday 11 AM = 10 hours
    # Friday: 8 hours
    # Weekend: 0 hours
    # Monday: 2 hours
    friday = datetime(2024, 1, 5, 9, 0, 0, tzinfo=UTC)
    monday = datetime(2024, 1, 8, 11, 0, 0, tzinfo=UTC)
    hours = calculate_work_hours_between(friday, monday, 8.0)
    assert abs(hours - 10.0) < 0.01


def test_calculate_work_hours_on_weekend() -> None:
    """Test calculating work hours entirely on weekend."""
    # Saturday 10 AM to Sunday 2 PM = 0 hours (no work on weekends)
    saturday = datetime(2024, 1, 6, 10, 0, 0, tzinfo=UTC)
    sunday = datetime(2024, 1, 7, 14, 0, 0, tzinfo=UTC)
    hours = calculate_work_hours_between(saturday, sunday, 8.0)
    assert hours == 0.0


def test_calculate_work_hours_backwards() -> None:
    """Test calculating work hours when end is before start."""
    start = datetime(2024, 1, 2, 9, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    hours = calculate_work_hours_between(start, end, 8.0)
    assert hours == 0.0


def test_work_calendar_class() -> None:
    """Test WorkCalendar wrapper class."""
    start_date = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    calendar = WorkCalendar(start_date)

    # Test add_hours
    end = calendar.add_hours(start_date, 4.0, 8.0)
    assert end == datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

    # Test hours_between
    hours = calendar.hours_between(start_date, end, 8.0)
    assert abs(hours - 4.0) < 0.01


def test_add_work_hours_multiple_weeks() -> None:
    """Test adding work hours that span multiple weeks."""
    # Monday Jan 1 + 80 hours (with 8 hour days) = 10 workdays later
    # Week 1: Mon 1, Tue 2, Wed 3, Thu 4, Fri 5 (40 hours)
    # Weekend 1: skipped
    # Week 2: Mon 8, Tue 9, Wed 10, Thu 11, Fri 12 (40 hours)
    # Total: 80 hours ending Friday Jan 12 at 5 PM
    monday = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    two_weeks_later = add_work_hours(monday, 80.0, 8.0)
    expected = datetime(2024, 1, 12, 17, 0, 0, tzinfo=UTC)  # Friday Jan 12, 5 PM
    assert two_weeks_later == expected


def test_add_work_hours_before_work_starts() -> None:
    """Test adding work hours when starting before work starts."""
    # Monday 7 AM (before work) + 4 hours = Monday 1 PM
    # Should move to 9 AM first, then add 4 hours
    monday_early = datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC)
    result = add_work_hours(monday_early, 4.0, 8.0)
    assert result == datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)


def test_add_work_hours_after_work_ends() -> None:
    """Test adding work hours when starting after work ends."""
    # Monday 6 PM (after 8-hour workday ends at 5 PM) + 2 hours = Tuesday 11 AM
    # Should move to next workday (Tuesday 9 AM), then add 2 hours
    monday_late = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
    result = add_work_hours(monday_late, 2.0, 8.0)
    assert result == datetime(2024, 1, 2, 11, 0, 0, tzinfo=UTC)


def test_calculate_work_hours_start_before_work_starts() -> None:
    """Test calculating work hours when start is before work starts."""
    # Monday 7 AM to Monday 1 PM
    # Work starts at 9 AM, so actual work hours are 9 AM to 1 PM = 4 hours
    start = datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
    hours = calculate_work_hours_between(start, end, 8.0)
    assert abs(hours - 4.0) < 0.01
