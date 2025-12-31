"""Calendar and work-time calculation utilities for simulation."""

from datetime import datetime, timedelta


def is_weekend(dt: datetime) -> bool:
    """Check if a datetime falls on a weekend.

    Args:
        dt: The datetime to check

    Returns:
        True if Saturday (5) or Sunday (6), False otherwise
    """
    return dt.weekday() >= 5


def skip_to_monday(dt: datetime) -> datetime:
    """Skip forward to the next Monday at the same time.

    Args:
        dt: A datetime on a weekend

    Returns:
        The next Monday at the same time of day
    """
    # Calculate days to add to get to Monday
    weekday = dt.weekday()
    if weekday == 5:  # Saturday
        days_to_add = 2
    elif weekday == 6:  # Sunday
        days_to_add = 1
    else:
        # Already a weekday, return as-is
        return dt

    return dt + timedelta(days=days_to_add)


def start_of_next_workday(dt: datetime) -> datetime:
    """Move to the start of the next workday.

    Args:
        dt: Current datetime

    Returns:
        The start of the next workday (9 AM on the next weekday)
    """
    # Move to next day at 9 AM
    next_day = (dt + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )

    # Skip weekend if necessary
    if is_weekend(next_day):
        next_day = skip_to_monday(next_day)

    return next_day


def add_work_hours(
    start: datetime, work_hours: float, hours_per_day: float
) -> datetime:
    """Add work hours to a datetime, skipping weekends.

    Args:
        start: Starting datetime
        work_hours: Number of work hours to add
        hours_per_day: Maximum work hours per day

    Returns:
        Datetime after adding the specified work hours
    """
    current = start
    hours_remaining = work_hours

    while hours_remaining > 0:
        # Skip to Monday if currently on weekend
        if is_weekend(current):
            current = skip_to_monday(current)
            continue

        # Calculate how many hours we can work today
        # Assume workday ends at start_hour + hours_per_day
        current_hour = current.hour + current.minute / 60.0 + current.second / 3600.0

        # Assume work starts at 9 AM
        work_start_hour = 9.0
        work_end_hour = work_start_hour + hours_per_day

        # How many hours left in today's workday?
        if current_hour < work_start_hour:
            # Before work starts, move to work start
            current = current.replace(
                hour=int(work_start_hour), minute=0, second=0, microsecond=0
            )
            hours_left_today = hours_per_day
        elif current_hour >= work_end_hour:
            # After work ends, move to next workday
            current = start_of_next_workday(current)
            continue
        else:
            # During work hours
            hours_left_today = work_end_hour - current_hour

        # Work as much as possible today
        hours_today = min(hours_remaining, hours_left_today)
        current += timedelta(hours=hours_today)
        hours_remaining -= hours_today

        if hours_remaining > 0:
            # Move to next workday
            current = start_of_next_workday(current)

    return current


def calculate_work_hours_between(
    start: datetime, end: datetime, hours_per_day: float
) -> float:
    """Calculate work hours between two datetimes, excluding weekends.

    Args:
        start: Start datetime
        end: End datetime
        hours_per_day: Work hours per day

    Returns:
        Total work hours between start and end
    """
    if end <= start:
        return 0.0

    total_hours = 0.0
    current = start
    work_start_hour = 9.0

    while current < end:
        # Skip weekends
        if is_weekend(current):
            current = skip_to_monday(current)
            continue

        # Calculate hours worked today
        current_hour = current.hour + current.minute / 60.0 + current.second / 3600.0
        work_end_hour = work_start_hour + hours_per_day

        # Determine working hours today
        if current_hour < work_start_hour:
            day_start = current.replace(
                hour=int(work_start_hour), minute=0, second=0, microsecond=0
            )
        else:
            day_start = current

        # End of workday today
        day_end = current.replace(
            hour=int(work_end_hour),
            minute=int((work_end_hour % 1) * 60),
            second=0,
            microsecond=0,
        )

        # Clip to actual end time
        day_end = min(day_end, end)

        # Add hours worked today
        if day_end > day_start:
            hours_today = (day_end - day_start).total_seconds() / 3600.0
            total_hours += hours_today

        # Move to next day
        current = start_of_next_workday(current)

        if current >= end:
            break

    return total_hours


class WorkCalendar:
    """Calendar for tracking work time in simulations."""

    def __init__(self, start_date: datetime) -> None:
        """Initialize the work calendar.

        Args:
            start_date: Project start date
        """
        self.start_date = start_date

    def add_hours(
        self, start: datetime, work_hours: float, hours_per_day: float
    ) -> datetime:
        """Add work hours to a datetime.

        Args:
            start: Starting datetime
            work_hours: Work hours to add
            hours_per_day: Hours per workday

        Returns:
            Datetime after adding work hours
        """
        return add_work_hours(start, work_hours, hours_per_day)

    def hours_between(
        self, start: datetime, end: datetime, hours_per_day: float
    ) -> float:
        """Calculate work hours between two datetimes.

        Args:
            start: Start datetime
            end: End datetime
            hours_per_day: Hours per workday

        Returns:
            Work hours between start and end
        """
        return calculate_work_hours_between(start, end, hours_per_day)
