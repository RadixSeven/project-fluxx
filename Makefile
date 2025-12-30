.PHONY: all_checks test coverage lint format type-check clean install help

# Default Python interpreter
PYTHON := python3

# Source and test directories
SRC_DIR := src/fluxx
TEST_DIR := tests

help:
	@echo "Project Fluxx - Makefile Commands"
	@echo ""
	@echo "  make all_checks    - Run all tests and static analysis, show incomplete coverage"
	@echo "  make test          - Run pytest with coverage"
	@echo "  make coverage      - Show coverage report (files not at 100%)"
	@echo "  make lint          - Run ruff linter"
	@echo "  make format        - Format code with ruff"
	@echo "  make type-check    - Run mypy type checker"
	@echo "  make install       - Install package in development mode"
	@echo "  make clean         - Remove generated files"
	@echo ""

install:
	@echo "==> Installing package in development mode..."
	pip install -e ".[dev]"

test:
	@echo "==> Running tests with coverage..."
	pytest $(TEST_DIR) \
		--cov=$(SRC_DIR) \
		--cov-report=term \
		--cov-report=html \
		--cov-report=json \
		-v

coverage:
	@echo "==> Coverage report (showing files not at 100%)..."
	@pytest $(TEST_DIR) \
		--cov=$(SRC_DIR) \
		--cov-report=term-missing \
		--cov-report=json \
		--quiet --quiet 2>/dev/null || true
	@echo ""
	@echo "Files with incomplete coverage:"
	@$(PYTHON) -c "import json; data = json.load(open('coverage.json')); files = data['files']; incomplete = {k: v for k, v in files.items() if v['summary']['percent_covered'] < 100}; [print(f'  {file:60s} {info[\"summary\"][\"percent_covered\"]:6.2f}% ({len(info[\"missing_lines\"])} lines missing)') for file, info in sorted(incomplete.items())] if incomplete else print('  All files have 100% coverage! ✓')"
	@echo ""

lint:
	@echo "==> Running ruff linter..."
	ruff check $(SRC_DIR) $(TEST_DIR)

format:
	@echo "==> Formatting code with ruff..."
	ruff format $(SRC_DIR) $(TEST_DIR)
	ruff check --fix $(SRC_DIR) $(TEST_DIR)

type-check:
	@echo "==> Running mypy type checker..."
	mypy --strict --ignore-missing-imports $(SRC_DIR) $(TEST_DIR)

all_checks: format lint type-check test coverage
	@echo ""
	@echo "========================================="
	@echo "All checks completed!"
	@echo "========================================="
	@echo ""

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
