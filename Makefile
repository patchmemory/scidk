# Convenience Makefile for docs/tools

.PHONY: flags-index docs-check unit integration check e2e-install-browsers e2e e2e-headed e2e-parallel e2e-debug clean-test-artifacts

flags-index:
	python -m dev.tools.feature_flags_index --write

# Clean up test artifacts (pytest sessions, cache, temp files)
# Keeps the 3 most recent pytest sessions
clean-test-artifacts:
	@echo "Cleaning test artifacts..."
	@# Remove pytest cache
	@rm -rf .pytest_cache
	@# Remove Python bytecode
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@# Keep last 3 pytest sessions, remove older ones
	@if [ -d "dev/test-runs/tmp/pytest-of-patch" ]; then \
		cd dev/test-runs/tmp/pytest-of-patch && \
		ls -t | grep '^pytest-[0-9]*$$' | tail -n +4 | xargs -r rm -rf ; \
	fi
	@# Remove playwright reports
	@rm -rf playwright-report test-results
	@echo "✓ Test artifacts cleaned (kept last 3 pytest sessions)"

# docs-check: run generator and diff; non-zero exit if mismatched
# Note: this target assumes Unix tools (diff)
docs-check:
	@mkdir -p dev/test-runs/tmp
	python -m dev.tools.feature_flags_index > dev/test-runs/tmp/feature-flags.md
	diff -q dev/test-runs/tmp/feature-flags.md dev/features/feature-flags.md

# Test tiers
unit:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp}
	TMPDIR=$$(pwd)/dev/test-runs/tmp \
	PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" \
	pytest -m "not integration and not e2e" -q

integration:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp}
	TMPDIR=$$(pwd)/dev/test-runs/tmp \
	PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" \
	pytest -m integration -q

check:
	$(MAKE) unit && $(MAKE) integration && $(MAKE) e2e

# Install Playwright browsers locally (no root/apt deps); install into repo cache
e2e-install-browsers:
	@mkdir -p dev/test-runs/{tmp,pw-browsers}
	PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers \
	TMPDIR=$$(pwd)/dev/test-runs/tmp \
	.venv/bin/python -m playwright install chromium

# Run headless E2E tests
# Requires a running server and BASE_URL to be set (e.g., http://localhost:5000)
e2e:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
	 SCIDK_E2E=1 TMPDIR=$$(pwd)/dev/test-runs/tmp TMP=$$(pwd)/dev/test-runs/tmp TEMP=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e -v --maxfail=1

# Run E2E tests in headed mode with Playwright inspector
e2e-headed:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
	SCIDK_E2E=1 PLAYWRIGHT_HEADLESS=0 PWDEBUG=1 TMPDIR=$$(pwd)/dev/test-runs/tmp TMP=$$(pwd)/dev/test-runs/tmp TEMP=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e -q

# Run E2E in parallel (requires pytest-xdist if desired; Playwright supports built-in workers)
e2e-parallel:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
	SCIDK_E2E=1 TMPDIR=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e -q -n auto || SCIDK_E2E=1 TMPDIR=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e -q

# Verbose debugging output for E2E runs
e2e-debug:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
	SCIDK_E2E=1 TMPDIR=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp -vv -s" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e

# Demo recording: runs a single E2E that captures screenshots and API JSON
# Artifacts go to dev/test-runs/last-demo by default (override with DEMO_ARTIFACTS_DIR)
demo-record:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
	SCIDK_E2E=1 DEMO_ARTIFACTS_DIR=$${DEMO_ARTIFACTS_DIR:-dev/test-runs/last-demo} TMPDIR=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e/test_demo_recording.py -q ; \
	echo "Artifacts saved under: $${DEMO_ARTIFACTS_DIR:-dev/test-runs/last-demo}"

# Demo recording in headed mode with inspector
demo-record-headed:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
	SCIDK_E2E=1 PLAYWRIGHT_HEADLESS=0 PWDEBUG=1 DEMO_ARTIFACTS_DIR=$${DEMO_ARTIFACTS_DIR:-dev/test-runs/last-demo} TMPDIR=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e/test_demo_recording.py -q ; \
	echo "Artifacts saved under: $${DEMO_ARTIFACTS_DIR:-dev/test-runs/last-demo}"
