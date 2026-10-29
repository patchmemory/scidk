# Human GUI UX checklist — Prompt 10

**Human results: not performed. No task is marked passed.**

Use the disposable server described in [GUI testing instructions](gui-testing.md).
It serves synthetic files and API responses, blocks all writes, and has no real
storage, Neo4j or provider connections. Do not substitute an institutional account
or production instance. Use the three target viewport sizes, then a narrower
window. Record browser/OS, viewport, participant role, date, elapsed time and
assistance needed. Do not record sensitive data in screenshots or notes.

Score each task with **Pass / Confusing / Broken / Not implemented**:

- **Pass:** completed unassisted; result and scope were understandable.
- **Confusing:** completed, but the route, wording or result needed explanation.
- **Broken:** an available control failed, lost context, or gave a misleading result.
- **Not implemented:** the intended task has no available control/backend in this build.

Expected limitations below are context, not human scores. Leave the Score column
blank until a person performs the task. A clear unavailable message can pass a
separate comprehension check while the requested operation remains Not implemented.

| Task | Suggested steps and observations | Current boundary | Score | Notes/time |
| --- | --- | --- | --- | --- |
| 1. Browse an accessible drive and locate a scientific dataset | Files → Synthetic drive → double-click the **vevo name** → metadata.xml. Then Datasets → search Vevo → select Synthetic Vevo study. Can you distinguish a file from a recognized Dataset? | Synthetic drive only; real recognition/storage authorization not exercised. | | |
| 2. Inspect filesystem and scientific metadata | Select metadata.xml; inspect size/path, modality and nested raw XML. Select the dataset; inspect acquisition frames and instrument. Is stored metadata distinguishable from confirmed knowledge? | Raw metadata is a text/JSON view, not a full scientific form or acceptance claim. | | |
| 3. Expand without losing selection | Switch inspector tabs, Expand, Restore docked inspector, switch Files/Datasets, Close, and reselect. Verify object, selected inspector tab and drive location. Repeat with keyboard. | In-page state only; cross-page persistence is not implemented. | | |
| 4. Find and use annotations | Open inspector Annotations; read Synthetic annotation. Locate the existing Annotate button on Files. Can you tell object annotations from attribution/collection tools? | No editing/writes in disposable fixture; annotation identity aliases remain unreconciled. | | |
| 5. Navigate from a dataset to related knowledge | Try to open related knowledge while retaining the selected dataset. Find the Knowledge destination and legacy Maps/Entities links. | Dataset-specific knowledge links/context transfer are not implemented. Legacy graph pages depend on external libraries/backends. | | |
| 6. Inspect a proposed assertion and evidence | Open Review; identify where assertion state, citation and human decisions would appear. | Review is a placeholder; no queue/evidence controls in this slice. Do not accept/materialize anything. | | |
| 7. Identify how to prepare a dataset for sharing | Select recognized dataset; find Prepare for Sharing and explain why it is unavailable. Can you distinguish the old whole-graph exporter? | Scoped exporter unavailable; legacy global export is not executed in this fixture. | | |
| 8. Understand implemented versus unavailable actions | Visit Overview, Resources, Knowledge, Review and Settings. Explain which pages work, which are placeholders, and whether disabled chat sends anything. | Overview chat unavailable; Resources shows an empty synthetic source list; Settings has a tracked offline CDN dependency. | | |

Additional observations (leave blank until performed):

| Check | Score | Notes |
| --- | --- | --- |
| Tab/Shift+Tab order, arrow/Home/End tab selection, visible focus | | |
| Enter/Space file inspection; Escape closes inspector and returns focus | | |
| Long metadata, raw markup and scrolling remain readable | | |
| Controls remain reachable at 1440×900, 1280×800, 1024×768 and narrower | | |
| Empty/loading/service-error/unavailable messages explain next steps | | |
| Screen reader announces tabs, selected state and panel labels | | |
| Screenshot candidates inspected; unexpected differences rejected | | |

For defects, record task, viewport, exact steps, expected/observed behavior,
severity and screenshot/trace path. Send findings for the next implementation
pass; this checklist does not approve Prompt 11, production deployment or any
new backend capability.
