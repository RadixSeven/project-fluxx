"""Tests for the Claude Code stop hook script."""

import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# Add hooks directory to path for importing
HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"


def _load_stop_check() -> ModuleType:
    """Dynamically load stop_check module from hooks directory."""
    spec = importlib.util.spec_from_file_location(
        "stop_check", HOOKS_DIR / "stop_check.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["stop_check"] = module
    spec.loader.exec_module(module)
    return module


stop_check = _load_stop_check()


class TestGetProjectDir:
    """Test get_project_dir function."""

    def test_returns_correct_project_root(self) -> None:
        """Project dir should be two levels up from the hook script."""
        project_dir = stop_check.get_project_dir()
        # The hook is in .claude/hooks/, so project is ../..
        # Accept either real project name or pants sandbox directory
        assert re.match(
            r"pants-sandbox-\w+|project_?fluxx", project_dir.name, re.IGNORECASE
        )


class TestGetStateFilePath:
    """Test get_state_file_path function."""

    def test_returns_path_in_hooks_directory(self) -> None:
        """State file should be in the .claude/hooks directory."""
        state_path = stop_check.get_state_file_path()
        assert state_path.parent == HOOKS_DIR
        assert state_path.name == ".last_check_state"


class TestGetCurrentRepoState:
    """Test get_current_repo_state function."""

    def test_returns_sha256_hash(self) -> None:
        """Should return a SHA256 hash string."""
        project_dir = stop_check.get_project_dir()
        state = stop_check.get_current_repo_state(project_dir)
        # SHA256 hex is 64 characters
        assert len(state) == 64
        assert all(c in "0123456789abcdef" for c in state)

    def test_returns_same_hash_for_unchanged_state(self) -> None:
        """Should return same hash when called twice with no changes."""
        project_dir = stop_check.get_project_dir()
        state1 = stop_check.get_current_repo_state(project_dir)
        state2 = stop_check.get_current_repo_state(project_dir)
        assert state1 == state2

    def test_handles_git_errors_gracefully(self) -> None:
        """Should return a hash even if git commands fail."""
        # Use a non-git directory
        state = stop_check.get_current_repo_state(Path("/tmp"))
        # Should still return a valid hash
        assert len(state) == 64

    def test_handles_subprocess_exception_for_git_rev_parse(self) -> None:
        """Should handle exception when git rev-parse subprocess fails."""
        with patch("subprocess.run", side_effect=OSError("Command not found")):
            state = stop_check.get_current_repo_state(Path("/tmp"))
            # Should still return a valid hash (empty content hashed)
            assert len(state) == 64

    def test_includes_untracked_file_contents(self, tmp_path: Path) -> None:
        """Should include untracked file contents in state hash."""
        # Create a fake git repo structure
        untracked_file = tmp_path / "untracked.txt"
        untracked_file.write_text("untracked content")

        # Mock git commands to simulate untracked files
        def mock_run(cmd: list[str], **kwargs: object) -> MagicMock:
            result = MagicMock()
            if "rev-parse" in cmd:
                result.returncode = 0
                result.stdout = "abc123"
            elif "diff" in cmd:
                result.returncode = 0
                result.stdout = ""
            elif "ls-files" in cmd:
                result.returncode = 0
                result.stdout = "untracked.txt"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            state = stop_check.get_current_repo_state(tmp_path)
            assert len(state) == 64

    def test_handles_nonexistent_untracked_file(self, tmp_path: Path) -> None:
        """Should skip untracked files that don't exist."""

        def mock_run(cmd: list[str], **kwargs: object) -> MagicMock:
            result = MagicMock()
            if "rev-parse" in cmd:
                result.returncode = 0
                result.stdout = "abc123"
            elif "diff" in cmd:
                result.returncode = 0
                result.stdout = ""
            elif "ls-files" in cmd:
                result.returncode = 0
                result.stdout = "nonexistent.txt"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            # nonexistent.txt doesn't exist, so is_file() returns False
            state = stop_check.get_current_repo_state(tmp_path)
            assert len(state) == 64

    def test_handles_exception_reading_untracked_file_content(
        self, tmp_path: Path
    ) -> None:
        """Should handle exception when read_text fails on untracked file."""
        # Create a file that exists but will fail to read
        untracked_file = tmp_path / "unreadable.txt"
        untracked_file.write_text("content")

        def mock_run(cmd: list[str], **kwargs: object) -> MagicMock:
            result = MagicMock()
            if "rev-parse" in cmd:
                result.returncode = 0
                result.stdout = "abc123"
            elif "diff" in cmd:
                result.returncode = 0
                result.stdout = ""
            elif "ls-files" in cmd:
                result.returncode = 0
                result.stdout = "unreadable.txt"
            return result

        with (
            patch("subprocess.run", side_effect=mock_run),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "read_text", side_effect=PermissionError("denied")),
        ):
            state = stop_check.get_current_repo_state(tmp_path)
            assert len(state) == 64

    def test_handles_exception_in_diff_block(self) -> None:
        """Should handle exception in the diff/untracked block."""
        # First call succeeds (rev-parse), second raises exception
        call_count = 0

        def mock_run(cmd: list[str], **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # rev-parse
                result = MagicMock()
                result.returncode = 0
                result.stdout = "abc123"
                return result
            else:  # diff or ls-files
                raise OSError("Git error")

        with patch("subprocess.run", side_effect=mock_run):
            state = stop_check.get_current_repo_state(Path("/tmp"))
            assert len(state) == 64


class TestGetSavedState:
    """Test get_saved_state function."""

    def test_returns_none_when_no_state_file(self) -> None:
        """Should return None if state file doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            result = stop_check.get_saved_state()
            assert result is None

    def test_returns_state_from_file(self) -> None:
        """Should return content from state file."""
        expected = "abc123"
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=expected + "\n"),
        ):
            result = stop_check.get_saved_state()
            assert result == expected

    def test_returns_none_when_read_fails(self) -> None:
        """Should return None if reading state file raises an exception."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", side_effect=PermissionError("denied")),
        ):
            result = stop_check.get_saved_state()
            assert result is None


class TestSaveCurrentState:
    """Test save_current_state function."""

    def test_writes_state_to_file(self) -> None:
        """Should write state hash to state file."""
        with patch.object(Path, "write_text") as mock_write:
            stop_check.save_current_state("test_hash_123")
            mock_write.assert_called_once_with("test_hash_123")

    def test_handles_write_errors_gracefully(self) -> None:
        """Should not raise on write errors, just log warning."""
        with (
            patch.object(Path, "write_text", side_effect=PermissionError("denied")),
            patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        ):
            # Should not raise
            stop_check.save_current_state("test_hash")
            assert "Warning" in mock_stderr.getvalue()


class TestHasChangesSinceLastCheck:
    """Test has_changes_since_last_check function."""

    def test_returns_true_when_no_saved_state(self) -> None:
        """Should return True if no previous state exists."""
        with (
            patch.object(stop_check, "get_current_repo_state", return_value="abc123"),
            patch.object(stop_check, "get_saved_state", return_value=None),
        ):
            has_changes, current = stop_check.has_changes_since_last_check(
                Path("/fake")
            )
            assert has_changes is True
            assert current == "abc123"

    def test_returns_false_when_state_matches(self) -> None:
        """Should return False if current state matches saved state."""
        with (
            patch.object(stop_check, "get_current_repo_state", return_value="abc123"),
            patch.object(stop_check, "get_saved_state", return_value="abc123"),
        ):
            has_changes, current = stop_check.has_changes_since_last_check(
                Path("/fake")
            )
            assert has_changes is False
            assert current == "abc123"

    def test_returns_true_when_state_differs(self) -> None:
        """Should return True if current state differs from saved state."""
        with (
            patch.object(stop_check, "get_current_repo_state", return_value="new_hash"),
            patch.object(stop_check, "get_saved_state", return_value="old_hash"),
        ):
            has_changes, current = stop_check.has_changes_since_last_check(
                Path("/fake")
            )
            assert has_changes is True
            assert current == "new_hash"


class TestBlockWithReason:
    """Test block_with_reason function."""

    def test_outputs_correct_json(self) -> None:
        """Should output JSON with decision and reason."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with pytest.raises(SystemExit) as exc_info:
                stop_check.block_with_reason("Test failure")

            assert exc_info.value.code == 0
            output = json.loads(mock_stdout.getvalue())
            assert output["decision"] == "block"
            assert output["reason"] == "Test failure"

    def test_escapes_special_characters(self) -> None:
        """Should properly escape special characters in JSON."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with pytest.raises(SystemExit):
                stop_check.block_with_reason('Error: "quoted"\nand newline')

            output = json.loads(mock_stdout.getvalue())
            assert '"quoted"' in output["reason"]
            assert "\n" in output["reason"]


class TestNotifyUserAndStop:
    """Test notify_user_and_stop function."""

    def test_outputs_to_stderr(self) -> None:
        """Should output error message to stderr."""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                stop_check.notify_user_and_stop("Setup failed")

            assert exc_info.value.code == 0
            assert "STOP HOOK ERROR: Setup failed" in mock_stderr.getvalue()

    def test_does_not_output_to_stdout(self) -> None:
        """Should not output anything to stdout (no blocking JSON)."""
        with (
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
            patch("sys.stderr", new_callable=io.StringIO),
            pytest.raises(SystemExit),
        ):
            stop_check.notify_user_and_stop("Setup failed")

        assert mock_stdout.getvalue() == ""


class TestGetVenvEnv:
    """Test get_venv_env function."""

    def test_sets_virtual_env(self) -> None:
        """Should set VIRTUAL_ENV environment variable."""
        venv_path = Path("/fake/venv")
        env = stop_check.get_venv_env(venv_path)
        assert env["VIRTUAL_ENV"] == "/fake/venv"

    def test_prepends_venv_bin_to_path(self) -> None:
        """Should prepend venv/bin to PATH."""
        venv_path = Path("/fake/venv")
        env = stop_check.get_venv_env(venv_path)
        assert env["PATH"].startswith("/fake/venv/bin:")

    def test_removes_pythonhome(self) -> None:
        """Should remove PYTHONHOME if present."""
        with patch.dict("os.environ", {"PYTHONHOME": "/some/path"}):
            venv_path = Path("/fake/venv")
            env = stop_check.get_venv_env(venv_path)
            assert "PYTHONHOME" not in env


def test_returns_existing_venv_path(tmp_path: Path) -> None:
    """Should return venv path if it already exists."""
    expected_venv_path = tmp_path / "venv"
    bin_path = expected_venv_path / "bin"
    activate_path = bin_path / "activate"
    expected_venv_path.mkdir()
    bin_path.mkdir()
    activate_path.touch()

    # Assuming venv exists in the test environment
    assert expected_venv_path.exists()
    venv_path = stop_check.ensure_venv(tmp_path)
    assert venv_path == expected_venv_path


class TestEnsureVenv:
    """Test ensure_venv function."""

    def test_notifies_user_when_activate_missing(self, tmp_path: Path) -> None:
        """Should notify user if venv exists but activate script is missing."""
        # Create venv directory without activate script
        venv_path = tmp_path / "venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        # Don't create activate script

        with (
            patch.object(stop_check, "notify_user_and_stop") as mock_notify,
        ):
            mock_notify.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                stop_check.ensure_venv(tmp_path)
            mock_notify.assert_called_once()
            assert "activate" in mock_notify.call_args[0][0].lower()

    def test_notifies_user_on_venv_creation_failure(self) -> None:
        """Should notify user if venv creation fails."""
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(stop_check, "run_command") as mock_run,
            patch.object(stop_check, "notify_user_and_stop") as mock_notify,
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stderr="python3.13 not found"
            )
            mock_notify.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                stop_check.ensure_venv(Path("/fake/project"))
            mock_notify.assert_called_once()
            assert "python3.13" in mock_notify.call_args[0][0]


class TestRunMakeInstall:
    """Test run_make_install function."""

    def test_calls_make_install(self) -> None:
        """Should call make install with correct arguments."""
        with (
            patch.object(stop_check, "run_command") as mock_run,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            stop_check.run_make_install(Path("/fake"), {"PATH": "/bin"})

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["make", "install"]

    def test_notifies_user_on_failure(self) -> None:
        """Should notify user if make install fails."""
        with (
            patch.object(stop_check, "run_command") as mock_run,
            patch.object(stop_check, "notify_user_and_stop") as mock_notify,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            mock_notify.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                stop_check.run_make_install(Path("/fake"), {})
            mock_notify.assert_called_once()


class TestRunPrecommit:
    """Test run_precommit function."""

    def test_returns_success_on_zero_exit(self) -> None:
        """Should return (True, output) on success."""
        with patch.object(stop_check, "run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Passed", stderr="")
            success, output = stop_check.run_precommit(Path("/fake"), {})
            assert success is True
            assert "Passed" in output

    def test_returns_failure_on_nonzero_exit(self) -> None:
        """Should return (False, output) on failure."""
        with patch.object(stop_check, "run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Failed")
            success, output = stop_check.run_precommit(Path("/fake"), {})
            assert success is False
            assert "Failed" in output


class TestRunPrecommitWithRetry:
    """Test run_precommit_with_retry function."""

    def test_succeeds_on_first_try(self) -> None:
        """Should not retry if first attempt succeeds."""
        with (
            patch.object(stop_check, "run_precommit") as mock_precommit,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_precommit.return_value = (True, "Passed")
            stop_check.run_precommit_with_retry(Path("/fake"), {})
        assert mock_precommit.call_count == 1

    def test_retries_once_on_first_failure(self) -> None:
        """Should retry once if first attempt fails."""
        with (
            patch.object(stop_check, "run_precommit") as mock_precommit,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_precommit.side_effect = [(False, "Failed"), (True, "Passed")]
            stop_check.run_precommit_with_retry(Path("/fake"), {})
        assert mock_precommit.call_count == 2

    def test_blocks_on_second_failure(self) -> None:
        """Should block if second attempt also fails."""
        with (
            patch.object(stop_check, "run_precommit") as mock_precommit,
            patch.object(stop_check, "block_with_reason") as mock_block,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_precommit.return_value = (False, "Still failing")
            mock_block.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                stop_check.run_precommit_with_retry(Path("/fake"), {})
            mock_block.assert_called_once()
            assert "twice" in mock_block.call_args[0][0].lower()


class TestRunAllChecks:
    """Test run_all_checks function."""

    def test_succeeds_on_zero_exit(self) -> None:
        """Should complete without blocking on success."""
        with (
            patch.object(stop_check, "run_command") as mock_run,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # Should not raise
            stop_check.run_all_checks(Path("/fake"), {})

    def test_blocks_on_failure(self) -> None:
        """Should block if make all_checks fails."""
        with (
            patch.object(stop_check, "run_command") as mock_run,
            patch.object(stop_check, "block_with_reason") as mock_block,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stdout="Test failed", stderr=""
            )
            mock_block.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                stop_check.run_all_checks(Path("/fake"), {})
            mock_block.assert_called_once()


class TestMain:
    """Test main function."""

    def test_exits_immediately_when_stop_hook_active(self) -> None:
        """Should exit 0 without running checks when stop_hook_active is true."""
        input_data = {"session_id": "test", "stop_hook_active": True}
        with patch("sys.stdin", io.StringIO(json.dumps(input_data))):
            with pytest.raises(SystemExit) as exc_info:
                stop_check.main()
            assert exc_info.value.code == 0

    def test_skips_checks_when_no_changes(self) -> None:
        """Should skip checks and exit when no changes since last check."""
        input_data = {"session_id": "test", "stop_hook_active": False}

        with (
            patch("sys.stdin", io.StringIO(json.dumps(input_data))),
            patch.object(
                stop_check,
                "has_changes_since_last_check",
                return_value=(False, "hash123"),
            ),
            patch.object(stop_check, "ensure_venv") as mock_venv,
            patch.object(stop_check, "notify_completion") as mock_notify,
            patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        ):
            with pytest.raises(SystemExit) as exc_info:
                stop_check.main()

            assert exc_info.value.code == 0
            # Should NOT run any checks
            mock_venv.assert_not_called()
            # Should notify about skipping
            mock_notify.assert_called_once_with(
                success=True, message="No changes - skipping checks."
            )
            assert "No changes since last check" in mock_stderr.getvalue()

    def test_runs_all_steps_when_changes_detected(self) -> None:
        """Should run all steps when changes are detected."""
        input_data = {"session_id": "test", "stop_hook_active": False}

        with (
            patch("sys.stdin", io.StringIO(json.dumps(input_data))),
            patch.object(
                stop_check,
                "has_changes_since_last_check",
                return_value=(True, "new_hash"),
            ),
            patch.object(stop_check, "ensure_venv") as mock_venv,
            patch.object(stop_check, "get_venv_env") as mock_env,
            patch.object(stop_check, "run_make_install") as mock_install,
            patch.object(stop_check, "run_precommit_with_retry") as mock_pre,
            patch.object(stop_check, "run_all_checks") as mock_checks,
            patch.object(stop_check, "save_current_state") as mock_save,
            patch.object(stop_check, "notify_completion") as mock_notify,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_venv.return_value = Path("/fake/venv")
            mock_env.return_value = {}
            with pytest.raises(SystemExit) as exc_info:
                stop_check.main()

            assert exc_info.value.code == 0
            mock_venv.assert_called_once()
            mock_env.assert_called_once()
            mock_install.assert_called_once()
            mock_pre.assert_called_once()
            mock_checks.assert_called_once()
            # Should save state after successful checks
            mock_save.assert_called_once_with("new_hash")
            mock_notify.assert_called_once_with(
                success=True, message="All checks passed! Ready to stop."
            )

    def test_does_not_save_state_on_check_failure(self) -> None:
        """Should not save state if checks fail (blocked)."""
        input_data = {"session_id": "test", "stop_hook_active": False}

        with (
            patch("sys.stdin", io.StringIO(json.dumps(input_data))),
            patch.object(
                stop_check,
                "has_changes_since_last_check",
                return_value=(True, "new_hash"),
            ),
            patch.object(stop_check, "ensure_venv") as mock_venv,
            patch.object(stop_check, "get_venv_env") as mock_env,
            patch.object(stop_check, "run_make_install"),
            patch.object(stop_check, "run_precommit_with_retry"),
            patch.object(stop_check, "run_all_checks") as mock_checks,
            patch.object(stop_check, "save_current_state") as mock_save,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            mock_venv.return_value = Path("/fake/venv")
            mock_env.return_value = {}
            # Simulate check failure by raising SystemExit (from block_with_reason)
            mock_checks.side_effect = SystemExit(0)

            with pytest.raises(SystemExit):
                stop_check.main()

            # Should NOT save state since checks failed
            mock_save.assert_not_called()


class TestIntegration:
    """Integration tests for the hook script."""

    def test_hook_script_exists(self) -> None:
        """Verify the hook script exists."""
        assert (HOOKS_DIR / "stop_check.py").exists()

    def test_shell_wrapper_exists(self) -> None:
        """Verify the shell wrapper exists."""
        assert (HOOKS_DIR / "stop-check.sh").exists()

    def test_stop_hook_active_bypass_via_subprocess(self) -> None:
        """Test that stop_hook_active=true exits immediately via subprocess."""
        result = subprocess.run(
            ["python3", str(HOOKS_DIR / "stop_check.py")],
            input=json.dumps({"session_id": "test", "stop_hook_active": True}),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout == ""
        # Should not have any "Running..." output since it exits early
        assert "Running" not in result.stderr


class TestRunCommand:
    """Test run_command function."""

    def test_captures_output(self) -> None:
        """Should capture stdout and stderr."""
        result = stop_check.run_command(["echo", "hello"], cwd=Path("."), env=None)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_uses_provided_cwd(self) -> None:
        """Should run command in specified directory."""
        result = stop_check.run_command(["pwd"], cwd=Path("/tmp"), env=None)
        assert "/tmp" in result.stdout

    def test_uses_provided_env(self) -> None:
        """Should use provided environment variables."""
        result = stop_check.run_command(
            ["bash", "-c", "echo $TEST_VAR"],
            cwd=Path("."),
            env={"TEST_VAR": "test_value", "PATH": "/bin:/usr/bin"},
        )
        assert "test_value" in result.stdout


class TestGetNtfyTopic:
    """Test get_ntfy_topic function."""

    def test_returns_none_when_not_set(self) -> None:
        """Should return None when BASE_NTFY_TOPIC is not set."""
        with patch.dict("os.environ", {}, clear=True):
            assert stop_check.get_ntfy_topic() is None

    def test_returns_full_topic_when_set(self) -> None:
        """Should return full topic with suffix when BASE_NTFY_TOPIC is set."""
        with patch.dict("os.environ", {"BASE_NTFY_TOPIC": "my-secret-base"}):
            topic = stop_check.get_ntfy_topic()
            assert topic == "my-secret-base-Claude-code-stop-hook"

    def test_uses_correct_suffix(self) -> None:
        """Should use the NTFY_TOPIC_SUFFIX constant."""
        with patch.dict("os.environ", {"BASE_NTFY_TOPIC": "test"}):
            topic = stop_check.get_ntfy_topic()
            assert topic is not None
            assert topic.endswith(stop_check.NTFY_TOPIC_SUFFIX)


class TestSendNtfyNotification:
    """Test send_ntfy_notification function."""

    def test_sends_request_to_correct_url(self) -> None:
        """Should send POST request to ntfy.sh with topic."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            result = stop_check.send_ntfy_notification("test-topic", "Hello")

            assert result is True
            mock_urlopen.assert_called_once()
            request = mock_urlopen.call_args[0][0]
            assert request.full_url == "https://ntfy.sh/test-topic"

    def test_sends_message_as_body(self) -> None:
        """Should send message as request body."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            stop_check.send_ntfy_notification("topic", "Test message")

            request = mock_urlopen.call_args[0][0]
            assert request.data == b"Test message"

    def test_sends_title_header(self) -> None:
        """Should include Title header."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MagicMock()
            stop_check.send_ntfy_notification("topic", "msg", title="My Title")

            request = mock_urlopen.call_args[0][0]
            assert request.get_header("Title") == "My Title"

    def test_returns_false_on_error(self) -> None:
        """Should return False and log error on failure."""
        with (
            patch("urllib.request.urlopen") as mock_urlopen,
            patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        ):
            mock_urlopen.side_effect = Exception("Network error")
            result = stop_check.send_ntfy_notification("topic", "msg")

            assert result is False
            assert "Failed to send ntfy notification" in mock_stderr.getvalue()


class TestNotifyCompletion:
    """Test notify_completion function."""

    def test_warns_when_topic_not_configured(self) -> None:
        """Should log warning when BASE_NTFY_TOPIC not set."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        ):
            stop_check.notify_completion(success=True, message="Done")

            stderr_output = mock_stderr.getvalue()
            assert "WARNING" in stderr_output
            assert "BASE_NTFY_TOPIC" in stderr_output

    def test_sends_notification_when_configured(self) -> None:
        """Should send notification when topic is configured."""
        with (
            patch.dict("os.environ", {"BASE_NTFY_TOPIC": "secret"}),
            patch.object(stop_check, "send_ntfy_notification") as mock_send,
        ):
            stop_check.notify_completion(success=True, message="All done")

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][0] == "secret-Claude-code-stop-hook"
            assert call_args[0][1] == "All done"
            assert "Passed" in call_args[0][2]

    def test_uses_failure_title_on_failure(self) -> None:
        """Should use failure title when success is False."""
        with (
            patch.dict("os.environ", {"BASE_NTFY_TOPIC": "secret"}),
            patch.object(stop_check, "send_ntfy_notification") as mock_send,
        ):
            stop_check.notify_completion(success=False, message="Failed")

            call_args = mock_send.call_args
            assert "Failed" in call_args[0][2]
