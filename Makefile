# Convenience Makefile for docs/tools

.PHONY: flags-index docs-check e2e-install-browsers e2e e2e-headed e2e-parallel e2e-debug

flags-index:
	python -m dev.tools.feature_flags_index --write

# docs-check: run generator and diff; non-zero exit if mismatched
# Note: this target assumes Unix tools (diff)
docs-check:
	python -m dev.tools.feature_flags_index > /tmp/feature-flags.md
	diff -q /tmp/feature-flags.md dev/features/feature-flags.md

# Install Playwright browsers (required for pytest-playwright)
e2e-install-browsers:
	python -m playwright install --with-deps

# Run headless E2E tests
# Ensures port 5001 is used by tests; app is auto-started by tests/e2e/conftest.py
e2e:
	pytest -m e2e tests/e2e -q

# Run E2E tests in headed mode with Playwright inspector
e2e-headed:
	PLAYWRIGHT_HEADLESS=0 PWDEBUG=1 pytest -m e2e tests/e2e -q

# Run E2E in parallel (requires pytest-xdist if desired; Playwright supports built-in workers)
e2e-parallel:
	pytest -m e2e tests/e2e -q -n auto || pytest -m e2e tests/e2e -q

# Verbose debugging output for E2E runs
e2e-debug:
	PYTEST_ADDOPTS="-vv -s" pytest -m e2e tests/e2e
