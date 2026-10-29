# Repeatable GUI validation

This foundation reuses the installed **Python Playwright** infrastructure from
`tests/test_gui_slice.py`. It adds no dependency and does not replace the older
TypeScript `e2e/` suite. That suite's global setup boots the full app with inherited
configuration and cleanup routes; it is unsuitable for this disconnected run.

`tests/gui/harness.py` registers the actual UI blueprint/templates/static assets
with explicit synthetic services and a read-only API allowlist. It never calls
`scidk.app.create_app`, initializes storage, reads institutional drives, or uses
provider/Neo4j credentials. Unknown APIs fail with 501; unknown UI routes fail
with 404; all writes fail with 405. Each test starts a disposable loopback server
on a random port. Browser requests outside that origin are blocked. This verifies
frontend behavior against fixture contracts, not production authentication,
recognition or backend correctness.

## Run

From the isolated worktree, using the existing project virtualenv:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui -q -o addopts='' --gui-artifacts /tmp/scidk-gui-run-001
```

Choose a **new, nonexistent artifact directory** each run. The harness refuses
to overwrite one. Chrome and loopback sockets may require execution permission
outside the sandbox. It uses `SCIDK_TEST_CHROME` if set, otherwise installed
`google-chrome`, otherwise Playwright's bundled Chromium. A missing browser fails
this required suite; it is not silently skipped. No browser download is automatic.
The original small intercepted test retains its historical skip behavior.

Runtime state tests without screenshots:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui/test_workflows.py -q -o addopts=''
```

Each run stores environment metadata, screenshots, comparison results, request/
browser-error logs and Playwright trace ZIPs. Existing Playwright tooling can open
traces locally. Inspect both screenshots and logs on failure. Unhandled JavaScript
exceptions, console errors, failed requests, unexpected HTTP errors and outside
requests fail teardown. The Settings test declares one exact known CDN request,
blocks it, and records a strict expected failure; unrelated errors still fail.
The explicit service-outage test permits only its exact expected HTTP-error path.
No general console/network-error suppression is used.

## Visual references and review

The 21 checked-in PNGs cover Overview, Files (selected file), Datasets (selected
dataset), expanded metadata, Resources, Knowledge and Review at **1440×900,
1280×800, 1024×768**. Initial references are provisional: **human approval pending**.
They are useful repeatability checkpoints, not approved UX or completed human tests.

Capture new candidates without touching references:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui/test_visuals.py -q -o addopts='' --gui-record-candidates --gui-artifacts /tmp/scidk-gui-candidates-001
```

Capture-only mode does **not** count as passing visual regression. Normal runs
compare to frozen `tests/gui/baselines/` references, never update them, and fail
when a reference is absent. Images use fixed locale/timezone/clock, light theme,
1× device scale, reduced motion, completed fonts and disabled screenshot animations.
The manifest records the capture environment; use matching browser/OS/fonts for
comparison. Cross-platform rendering equivalence is not promised.

Comparison uses browser Canvas, so no new image package is needed. A pixel counts
as changed if a color channel differs by more than 24; more than **0.2%** changed
pixels or different dimensions fails. This catches large visual changes, not all
small defects. A detector test verifies a deliberately changed page is rejected.
Separate checks catch horizontal overflow, out-of-viewport navigation/inspector
controls, and an obscured dataset Search button.

To change references: inspect old/current images and traces, determine whether
changes are intentional, obtain human review, record reviewer/date/reason in the
manifest, and copy only approved images in a dedicated reviewed change. **There
is no auto-approve/update-baselines flag.** A browser/font upgrade requires the
same candidate/review process, not a relaxed pixel threshold.

## Human session

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m tests.gui.harness --port 5075
```

Visit `http://127.0.0.1:5075/overview` and use the
[human UX checklist](gui-human-ux-checklist.md). Stop the server with Ctrl+C.
This is an optional localhost-only test server, not a deployment command. Manual
browsers lack the automated request guard: legacy Settings/Maps may attempt CDN
requests. Use browser offline controls/firewall for a fully disconnected manual
session; do not supply real backend settings or credentials. Writes are refused.
