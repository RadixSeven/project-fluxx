#!/usr/bin/env python3
"""
Claude Code notification hook for permission requests.

Sends an ntfy notification when Claude needs user input (permission prompts).
"""

import json
import os
import sys
import urllib.request

NTFY_TOPIC_SUFFIX = "Claude-code-needs-input"


def get_ntfy_topic() -> str | None:
    """Get the ntfy topic from environment. Returns None if not configured."""
    base_topic = os.environ.get("BASE_NTFY_TOPIC")
    if base_topic:
        return f"{base_topic}-{NTFY_TOPIC_SUFFIX}"
    return None


def send_ntfy_notification(
    topic: str, message: str, title: str = "Claude Code"
) -> bool:
    """Send a notification via ntfy.sh. Returns True on success."""
    url = f"https://ntfy.sh/{topic}"
    try:
        request = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            headers={"Title": title},
            method="PUT",
        )
        urllib.request.urlopen(request, timeout=10)
        return True
    except Exception as e:
        print(f"Failed to send ntfy notification: {e}", file=sys.stderr)
        return False


def main() -> None:
    """Main entry point."""
    # Read input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Get the notification message
    message = input_data.get("message", "Claude Code needs your input")

    # Send notification
    topic = get_ntfy_topic()
    if topic is None:
        print(
            "WARNING: BASE_NTFY_TOPIC not set. "
            "Set this environment variable to receive notifications.",
            file=sys.stderr,
        )
        sys.exit(0)

    send_ntfy_notification(topic, message, title="Claude Code - Needs Input")
    sys.exit(0)


if __name__ == "__main__":
    main()
