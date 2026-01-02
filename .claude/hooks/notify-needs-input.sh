#!/bin/bash
# Shell wrapper for the notification hook
exec python3 "$(dirname "$0")/notify_needs_input.py"
