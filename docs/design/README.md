# SciDK GUI v3.1 handoff bundle

Copy `scidk-gui-v3.html` and `scidk-gui-v3-spec.md` to `docs/design/`.

Apply the text in `vision-v1.1-addendum.md` to `docs/vision/scidk-vision-v1.1.md` (or retain as a linked addendum). Apply `nci-2026-demo-addendum.md` to `docs/demo/nci-2026-demo-plan.md`.

Copy `codex_prompt_08.md` into your prompt directory and ask Codex to read and execute it. `gui-followon-pass-index.md` is planning only. `development-cost-checkpoints.md` is a research/benchmarking record.

The HTML is a **static synthetic-data design reference**; do not copy its fake API behavior into SciDK.

Implemented first slice: [migration map](scidk-gui-migration-map.md) and
[implementation/validation report](gui-first-slice-report.md). The addenda remain
linked authoritative inputs for this pass; the original vision/demo documents in
the primary checkout were not edited. The executable user request was
`codex_prompt_09.txt` (its internal heading says Prompt 08).
