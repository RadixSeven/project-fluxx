.PHONY: all_checks test coverage verify-coverage lint format type-check clean install help regenerate-suppressions

# Use bash for process substitution support
SHELL := /bin/bash

# Default Python interpreter
PYTHON := python3

# Source and test directories
SRC_DIR := src/fluxx
TEST_DIR := tests

# Coverage check script (exported as environment variable for use in shell)
define COVERAGE_CHECK_SCRIPT
import json, sys
data = json.load(open('coverage.json'))
failed = False
for path, info in sorted(data['files'].items()):
    pct = info['summary']['percent_covered']
    is_gui = '/gui/' in path
    if is_gui:
        if pct < 90:
            print(f'  FAIL: {path}: {pct:.2f}% (requires >=90%)')
            failed = True
    else:
        if pct < 100:
            print(f'  FAIL: {path}: {pct:.2f}% (requires 100%)')
            failed = True
sys.exit(1 if failed else 0)
endef
export COVERAGE_CHECK_SCRIPT

help:
	@echo "Project Fluxx - Makefile Commands"
	@echo ""
	@echo "  make all_checks              - Run all tests and static analysis, verify coverage"
	@echo "  make test                    - Run pytest with coverage"
	@echo "  make coverage                - Show coverage report (files not at 100%)"
	@echo "  make verify-coverage         - Verify coverage thresholds and suppression list"
	@echo "  make lint                    - Run ruff linter"
	@echo "  make format                  - Format code with ruff"
	@echo "  make type-check              - Run mypy type checker"
	@echo "  make install                 - Install package in development mode"
	@echo "  make regenerate-suppressions - Regenerate allowed suppression list (human review required)"
	@echo "  make clean                   - Remove generated files"
	@echo ""

install:
	@echo "==> Installing package in development mode..."
	pip install -e ".[dev]"

test:
	@echo "==> Running tests with coverage..."
	# The QT_QPA_PLATFORM=offscreen keeps the tests
	# from crashing in restricted sandboxes like those
	# used by `claude` and `codex`
	QT_QPA_PLATFORM=offscreen pytest $(TEST_DIR) \
		--cov=$(SRC_DIR) \
		--cov-report=term \
		--cov-report=html \
		--cov-report=json \
		-v

coverage:
	@echo "==> Coverage report (showing files not at 100%)..."
	# The QT_QPA_PLATFORM=offscreen keeps the tests
	# from crashing in restricted sandboxes like those
	# used by `claude` and `codex`
	@QT_QPA_PLATFORM=offscreen pytest $(TEST_DIR) \
		--cov=$(SRC_DIR) \
		--cov-report=term-missing \
		--cov-report=json \
		--quiet --quiet 2>/dev/null || true
	@echo ""
	@echo "Files with incomplete coverage:"
	@$(PYTHON) -c "import json; data = json.load(open('coverage.json')); files = data['files']; incomplete = {k: v for k, v in files.items() if v['summary']['percent_covered'] < 100}; [print(f'  {file:60s} {info[\"summary\"][\"percent_covered\"]:6.2f}% ({len(info[\"missing_lines\"])} lines missing)') for file, info in sorted(incomplete.items())] if incomplete else print('  All files have 100% coverage! ✓')"
	@echo ""

verify-coverage:
	@echo "==> Verifying coverage thresholds and suppression list..."
	@if [ -f dont_commit_waiting_for_review ]; then \
		echo "  [BYPASS] dont_commit_waiting_for_review exists - skipping verification"; \
		echo "  WARNING: Remove this file and update allowed_static_analysis_suppression.txt before committing"; \
	else \
		if ! $(PYTHON) -c "$$COVERAGE_CHECK_SCRIPT"; then \
			echo "Coverage thresholds not met!"; \
			exit 1; \
		fi; \
		echo "  Coverage thresholds: OK"; \
		CURRENT_SUPPRESSIONS=$$(find . \( -name "*.md" -o -name "*.py" -o -name "Makefile*" -o -name "*.toml" -o -name "*.yaml" -o -name "*.json" \) -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.mypy_cache/*" -exec grep -Hn "type: ignore\|pragma: no cover\|[\[(:,t][[:space:]]*Any\b" {} + 2>/dev/null | sed 's|^\./||' | sort -t: -k1,1 -k2,2n | sed 's/^\([^:]*\):[0-9]*:/\1:/'); \
		DIFF_OUTPUT=$$(diff <(echo "$$CURRENT_SUPPRESSIONS") allowed_static_analysis_suppression.txt 2>&1) || true; \
		if [ -n "$$DIFF_OUTPUT" ]; then \
			NEW_SUPPRESSIONS=$$(echo "$$DIFF_OUTPUT" | grep "^<" || true); \
			REMOVED_SUPPRESSIONS=$$(echo "$$DIFF_OUTPUT" | grep "^>" || true); \
			if [ -n "$$NEW_SUPPRESSIONS" ]; then \
				echo "  FAIL: New suppressions detected!"; \
				echo "  New entries:"; \
				echo "$$NEW_SUPPRESSIONS" | sed 's/^< /    /'; \
				if [ -n "$$REMOVED_SUPPRESSIONS" ]; then \
					echo "  Removed entries (informational):"; \
					echo "$$REMOVED_SUPPRESSIONS" | sed 's/^> /    /'; \
				fi; \
				echo ""; \
				echo "  To add new suppressions or documentation mentioning suppressions:"; \
				echo "    1. Create file: touch dont_commit_waiting_for_review"; \
				echo "    2. Run checks (will pass with bypass)"; \
				echo "    3. Have a human review the changes"; \
				echo "    4. Have a human update the suppression list:"; \
				echo "       make regenerate-suppressions"; \
				echo "    5. Have the human remove the bypass and commit the updated list:"; \
				echo "       rm dont_commit_waiting_for_review"; \
				echo "       git add allowed_static_analysis_suppression.txt"; \
				echo "       git commit"; \
				exit 1; \
			elif [ -n "$$REMOVED_SUPPRESSIONS" ]; then \
				echo -e "  \033[5;38;5;208mWARNING: Some suppressions have been removed from the codebase:\033[0m"; \
				echo "$$REMOVED_SUPPRESSIONS" | sed 's/^> /    /'; \
				echo -e "  \033[5;38;5;208mRun 'make regenerate-suppressions' to update the list.\033[0m"; \
				echo "  Suppression list: OK (with warnings)"; \
			fi; \
		else \
			echo "  Suppression list: OK"; \
		fi; \
		if git diff --name-only | grep -q "allowed_static_analysis_suppression.txt"; then \
			echo "  FAIL: allowed_static_analysis_suppression.txt has uncommitted changes!"; \
			echo "  A human must review and commit changes to the suppression list."; \
			exit 1; \
		fi; \
		if git diff --cached --name-only | grep -q "allowed_static_analysis_suppression.txt"; then \
			echo "  FAIL: allowed_static_analysis_suppression.txt is staged but not committed!"; \
			echo "  A human must review and commit changes to the suppression list."; \
			exit 1; \
		fi; \
		echo "  Suppression list not modified: OK"; \
		echo "  All coverage checks passed!"; \
	fi

lint:
	@echo "==> Running ruff linter..."
	ruff check $(SRC_DIR) $(TEST_DIR)

format:
	@echo "==> Formatting code with ruff..."
	ruff format $(SRC_DIR) $(TEST_DIR)
	ruff check --fix $(SRC_DIR) $(TEST_DIR)

type-check:
	@echo "==> Running mypy type checker..."
	mypy --strict $(SRC_DIR) $(TEST_DIR)

all_checks: format lint type-check test coverage verify-coverage
	@echo ""
	@echo "========================================="
	@echo "All checks completed!"
	@echo "========================================="
	@echo ""

regenerate-suppressions:
	@echo "==> Regenerating allowed_static_analysis_suppression.txt..."
	@find . \( -name "*.md" -o -name "*.py" -o -name "Makefile*" -o -name "*.toml" -o -name "*.yaml" -o -name "*.json" \) \
		-type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.mypy_cache/*" \
		-exec grep -Hn "type: ignore\|pragma: no cover\|[\[(:,t][[:space:]]*Any\b" {} + 2>/dev/null \
		| sed 's|^\./||' \
		| sort -t: -k1,1 -k2,2n \
		| sed 's/^\([^:]*\):[0-9]*:/\1:/' \
		> allowed_static_analysis_suppression.txt
	@echo "  Done. Review and commit allowed_static_analysis_suppression.txt"

clean:
	@echo "==> Cleaning generated files..."
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.json
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	rm -rf src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete."
