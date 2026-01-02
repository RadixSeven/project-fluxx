#!/bin/bash
# Shell wrapper for Python stop hook
# This wrapper ensures we use the system Python (not venv) to run the hook

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/stop_check.py"
