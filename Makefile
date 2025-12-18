# Convenience Makefile for docs/tools

.PHONY: flags-index docs-check unit integration check e2e-install-browsers e2e e2e-headed e2e-parallel e2e-debug

flags-index:
	python -m dev.tools.feature_flags_index --write

# docs-check: run generator and diff; non-zero exit if mismatched
# Note: this target assumes Unix tools (diff)
docs-check:
	python -m dev.tools.feature_flags_index > /tmp/feature-flags.md
	diff -q /tmp/feature-flags.md dev/features/feature-flags.md

# Test tiers
unit:
	pytest -m "not integration and not e2e" -q

integration:
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
# Ensures port 5001 is used by tests; app is auto-started by tests/e2e/conftest.py
e2e:
	@mkdir -p dev/test-runs/{tmp,pytest-tmp,artifacts,downloads,pw-browsers}
 SCIDK_E2E=1 TMPDIR=$$(pwd)/dev/test-runs/tmp TMP=$$(pwd)/dev/test-runs/tmp TEMP=$$(pwd)/dev/test-runs/tmp PYTEST_ADDOPTS="--basetemp=$$(pwd)/dev/test-runs/pytest-tmp" PLAYWRIGHT_BROWSERS_PATH=$$(pwd)/dev/test-runs/pw-browsers pytest -m e2e tests/e2e -q

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
