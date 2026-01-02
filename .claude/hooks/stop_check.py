#!/usr/bin/env python3
"""
Claude Code stop hook for ProjectFluxx.

Ensures venv is set up, pre-commit passes, and all checks pass before allowing stop.
Only runs checks if files have changed since the last successful run.
"""

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

NTFY_TOPIC_SUFFIX = "Claude-code-stop-hook"
STATE_FILE_NAME = ".last_check_state"


def get_project_dir() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def get_state_file_path() -> Path:
    """Get the path to the state file that tracks last successful check."""
    return Path(__file__).parent / STATE_FILE_NAME


def get_current_repo_state(project_dir: Path) -> str:
    """Get a hash representing the current state of the repository.

    Combines the HEAD commit hash with a hash of all uncommitted changes
    (both staged and unstaged) to create a unique fingerprint.
    """
    # Get HEAD commit hash
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        head_hash = head_result.stdout.strip() if head_result.returncode == 0 else ""
    except Exception:
        head_hash = ""

    # Get diff of all changes (staged + unstaged + untracked)
    try:
        # Get staged and unstaged changes
        diff_result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        diff_content = diff_result.stdout if diff_result.returncode == 0 else ""

        # Get untracked files and their contents for completeness
        untracked_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        untracked_files = (
            untracked_result.stdout.strip().split("\n")
            if untracked_result.returncode == 0 and untracked_result.stdout.strip()
            else []
        )

        # Hash untracked file contents
        untracked_content = ""
        for filepath in untracked_files:
            full_path = project_dir / filepath
            if full_path.is_file():
                try:
                    untracked_content += f"\n--- {filepath} ---\n"
                    untracked_content += full_path.read_text(errors="replace")
                except Exception:
                    pass

    except Exception:
        diff_content = ""
        untracked_content = ""

    # Combine and hash
    combined = f"{head_hash}\n{diff_content}\n{untracked_content}"
    return hashlib.sha256(combined.encode()).hexdigest()


def get_saved_state() -> str | None:
    """Get the saved state from the last successful check."""
    state_file = get_state_file_path()
    if state_file.exists():
        try:
            return state_file.read_text().strip()
        except Exception:
            return None
    return None


def save_current_state(state_hash: str) -> None:
    """Save the current state hash after successful checks."""
    state_file = get_state_file_path()
    try:
        state_file.write_text(state_hash)
    except Exception as e:
        print(f"Warning: Could not save state file: {e}", file=sys.stderr)


def has_changes_since_last_check(project_dir: Path) -> tuple[bool, str]:
    """Check if there are changes since the last successful check.

    Returns (has_changes, current_state_hash).
    """
    current_state = get_current_repo_state(project_dir)
    saved_state = get_saved_state()

    if saved_state is None:
        return True, current_state

    return current_state != saved_state, current_state


def read_input() -> dict[str, object]:
    """Read JSON input from stdin."""
    return json.load(sys.stdin)  # type: ignore[no-any-return]


def block_with_reason(reason: str) -> None:
    """Output blocking JSON and exit."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def notify_user_and_stop(message: str) -> None:
    """Notify user of setup problems via stderr and allow stop."""
    print(f"STOP HOOK ERROR: {message}", file=sys.stderr)
    sys.exit(0)


def run_command(
    cmd: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def ensure_venv(project_dir: Path) -> Path:
    """Ensure python3.13 venv exists, create if needed. Returns venv path."""
    venv_path = project_dir / "venv"

    if not venv_path.exists():
        print("Creating python3.13 venv...", file=sys.stderr)
        result = run_command(["python3.13", "-m", "venv", "venv"], cwd=project_dir)
        if result.returncode != 0:
            notify_user_and_stop(
                f"Failed to create python3.13 venv. Is python3.13 installed?\n"
                f"{result.stderr}"
            )

    activate_script = venv_path / "bin" / "activate"
    if not activate_script.exists():
        notify_user_and_stop("venv/bin/activate not found. Venv may be corrupted.")

    return venv_path


def get_venv_env(venv_path: Path) -> dict[str, str]:
    """Get environment dict with venv activated."""
    env = os.environ.copy()
    venv_bin = venv_path / "bin"
    env["VIRTUAL_ENV"] = str(venv_path)
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    env.pop("PYTHONHOME", None)
    return env


def run_make_install(project_dir: Path, env: dict[str, str]) -> None:
    """Run make install."""
    print("Running make install...", file=sys.stderr)
    result = run_command(["make", "install"], cwd=project_dir, env=env)
    if result.returncode != 0:
        notify_user_and_stop(
            f"make install failed. Check Makefile and dependencies.\n"
            f"{result.stdout}\n{result.stderr}"
        )


def run_precommit(project_dir: Path, env: dict[str, str]) -> tuple[bool, str]:
    """Run pre-commit. Returns (success, output)."""
    result = run_command(["pre-commit", "run", "--all-files"], cwd=project_dir, env=env)
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def run_precommit_with_retry(project_dir: Path, env: dict[str, str]) -> None:
    """Run pre-commit, retry once if it fails (for auto-fixes)."""
    print("Running pre-commit...", file=sys.stderr)
    success, output = run_precommit(project_dir, env)

    if not success:
        print("Pre-commit failed, retrying (for auto-fixes)...", file=sys.stderr)
        success, output = run_precommit(project_dir, env)

        if not success:
            block_with_reason(
                f"Pre-commit failed twice. Please fix the following issues:\n\n{output}"
            )


def run_all_checks(project_dir: Path, env: dict[str, str]) -> None:
    """Run make all_checks."""
    print("Running make all_checks...", file=sys.stderr)
    result = run_command(["make", "all_checks"], cwd=project_dir, env=env)

    if result.returncode != 0:
        output = result.stdout + result.stderr
        block_with_reason(
            f"make all_checks failed. Please fix the following issues:\n\n{output}"
        )


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


def notify_completion(success: bool, message: str) -> None:
    """Send completion notification if ntfy is configured."""
    topic = get_ntfy_topic()
    if topic is None:
        print(
            "WARNING: BASE_NTFY_TOPIC not set. "
            "Set this environment variable to receive notifications.",
            file=sys.stderr,
        )
        return

    title = "Claude Code - Checks Passed" if success else "Claude Code - Checks Failed"
    send_ntfy_notification(topic, message, title)


def main() -> None:
    """Main entry point."""
    # Read input
    input_data = read_input()

    # Prevent infinite loops
    if input_data.get("stop_hook_active") is True:
        sys.exit(0)

    project_dir = get_project_dir()

    # Check if there are changes since last successful check
    has_changes, current_state = has_changes_since_last_check(project_dir)

    if not has_changes:
        print("No changes since last check. Skipping tests.", file=sys.stderr)
        notify_completion(success=True, message="No changes - skipping checks.")
        sys.exit(0)

    # Step 1-2: Ensure venv exists and get activated environment
    venv_path = ensure_venv(project_dir)
    env = get_venv_env(venv_path)

    # Step 3: Run make install
    run_make_install(project_dir, env)

    # Step 4: Run pre-commit with retry
    run_precommit_with_retry(project_dir, env)

    # Step 5: Run make all_checks
    run_all_checks(project_dir, env)

    # All checks passed - save state for next time
    save_current_state(current_state)
    print("All checks passed!", file=sys.stderr)
    notify_completion(success=True, message="All checks passed! Ready to stop.")
    sys.exit(0)


if __name__ == "__main__":
    main()
