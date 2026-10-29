# GUI validation foundation — codex_prompt_10.txt

Built from `f83dae1a073ed2d105a764de8ffd0e4651924d15` in the existing isolated
`design/knowledge-curation-20261029` worktree. No Prompt 11 features were started.

## Result

The reusable browser suite exercises real UI routes, templates and JavaScript over
a disposable HTTP server with synthetic scientific files/datasets/annotations.
It reuses installed Python Playwright and the first slice's app fixture (now a
shared factory). No new package, production app factory, storage scan, provider,
Neo4j connection, database migration or authorization change is involved.

The server binds loopback on an allocated port, allows only designated UI routes,
serves explicit synthetic APIs and refuses writes. The automated browser also
blocks all outside-origin requests. Unknown requests and browser/console failures
fail tests. The fixture has no production services to call. The older TypeScript
E2E infrastructure was inspected and preserved; its full-app startup and cleanup
are deliberately not invoked by this disconnected suite.

## Coverage

- All six destination links, actual browser navigation including legacy Settings,
  plus HTTP continuity of preserved routes and compatibility redirects.
- Drive/folder browsing and actual DOM file selection; Dataset search/selection;
  Files/Datasets switching with drive path and per-tab selections retained.
- Inspector Metadata, Annotations and Provenance, raw text/XML safety, expansion,
  restore, close/reopen, selection retention, and unavailable sharing.
- Keyboard Enter/Space selection, arrow/Home/End tab behavior, panel associations,
  selected/roving-tab state, visible focus, Escape and focus return.
- A narrower 800×700 interaction check and three deterministic screenshot sizes:
  1440×900, 1280×800, 1024×768.
- Loading, empty, explicit service-error, disabled chat/sharing and placeholder
  Knowledge/Review states. No question, tool or DMS export is sent by the new GUI.
- Console/page exceptions, failed requests, unexpected HTTP responses and egress.
- Twenty-one screenshot comparisons, dimension/major-pixel-change detection,
  horizontal overflow, visible controls and dataset Search hit testing. A deliberate
  color change verifies the image comparator actually rejects changes.

## Discovered issues and scoped fixes

| ID | Finding | Disposition |
| --- | --- | --- |
| GUI-001 | ARIA tabs lacked arrow/Home/End navigation, roving focus and explicit panel associations. | Fixed in the new shell; legacy drawer semantics are outside this audit. |
| GUI-002 | File rows were mouse-only; inspector had no Escape dismissal/focus return. | Added focusable named rows, Enter/Space inspection, visible focus and Escape return to the initiating control. |
| GUI-003 | At 1024 pixels, the dataset inspector covered Search. | Reserve space for the Dataset pane, assert Search hit testing, and place inspector in normal flow below 900 pixels. |
| GUI-004 | Legacy Settings requests external Cytoscape from unpkg.com, preventing a fully disconnected page. Other legacy graph pages have similar CDN dependencies. | Deferred: migrate/test graph assets in a focused later pass. The exact Settings dependency is blocked and tracked as a strict expected failure. Its test must be removed/updated when fixed; unrelated exceptions still fail. |
| GUI-005 | Opening the docked inspector after the first folder click could intercept the second click at 1024 pixels. | Delay folder mouse inspection 400ms and cancel it on double-click so navigation completes. Keyboard inspection stays immediate. The shared pending timer is cancelled on new selections and list renders. Full-row double-click is now tested at all three widths. |

Known capability gaps remain explicit: Overview conversational transport,
dataset-scoped DMS, dataset-to-knowledge context transfer, actual Review queue/
assertion evidence controls, and live scientific recognition. These were not
implemented or silently treated as successful workflows. Annotation editing is
not exercised in the read-only fixture; the current inspector reads stored notes
and preserves the legacy Annotate entry point. Screen-reader behavior and broader
legacy administration/graph interactions still require human/future review.
Keyboard file inspection is covered; the legacy browser still lacks a keyboard
shortcut for entering folders (mouse double-click remains necessary). This
remaining keyboard traversal gap needs a focused accessibility follow-up.

## Visual and human review

Initial [reference gallery](../../tests/gui/baselines/index.html): 21 PNGs plus
browser/environment metadata and SHA-256 hashes. They are **provisional initial
references; human approval is pending**. Comparison captures never overwrite
references. Changed candidates need explicit review; there is no auto-accept flag.
The references detect regressions in this environment, not cross-platform pixel
equivalence or clinical/scientific validation. The 0.2% changed-pixel threshold
ignores channel differences up to 24; smaller defects can require manual review.

[Human UX checklist](gui-human-ux-checklist.md): realistic tasks with
Pass / Confusing / Broken / Not implemented scoring. All human scores remain
blank. Automated checks do not imply human acceptance. Dataset-related knowledge
navigation and proposed-assertion evidence inspection are listed with their actual
unimplemented boundaries.

## Execution and results

Non-browser regression: **128 passed, 0 failed, 0 skipped, 1 deselected** in
28.21 seconds. The deselected test is the original intercepted browser test; it
passed separately during focused validation and is superseded here by the new
HTTP browser suite. Final browser results are recorded below separately. Capture-only development runs are not counted as visual
regression passes. Browser environment: Linux, system Chrome 152.0.7977.82,
Playwright Python, en-US, UTC, 1× scale, light theme, fixed Date.now and synthetic
fixture version 1. No automatic browser installation was performed.

See [execution instructions](gui-testing.md) for repeat runs, candidate capture,
trace inspection and the optional local human-test server. The final browser run
stores PNGs, diff JSON, traces and request/error logs at
`/tmp/scidk-gui10-final-browser-verified` (local artifacts, not committed).

Changed runtime files are limited to `gui_slice.js`, `gui_slice.css`,
`files/datasets.html` and `gui/files_inspector.html`. Test changes add the shared
factory, loopback/browser fixtures, workflows, comparator and 21 frozen references;
`tests/test_gui_slice.py` reuses the shared factory. Documentation adds this report,
testing instructions, human checklist and cost checkpoint. The focused commit's
exact hash is recorded in the completion response; it includes this report.


Final browser regression: **28 passed, 0 failed, 0 skipped, 1 expected failure**
in 38.56 seconds. The sole expected failure is GUI-004; it does not count as a
working disconnected Settings page. All 21 reference comparisons passed with
**0 changed pixels** in the recorded environment. Initial reference capture-only
runs were excluded from this result. The original first-slice GUI suite also
passed (3 tests) during focused compatibility validation.

Final commands:

```sh
python -m pytest tests/gui -q -o addopts='' --gui-artifacts /tmp/scidk-gui10-final-browser-verified
python -m pytest tests/test_gui_slice.py -k 'not test_browser_selection_and_inspector' tests/pipeline/test_mapping_ui.py tests/pipeline/test_canvas_context.py tests/test_annotations_rest_endpoints.py tests/test_annotations_and_selections.py tests/test_nih_dms_plan.py tests/knowledge_e2e -q -o addopts=''
```

JavaScript syntax and Git whitespace checks passed. The primary checkout's
modified `dev` and untracked user inputs are preserved. Human UX time/cost and
approval have not been supplied. No later GUI slice has started.
