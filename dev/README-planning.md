id: doc:planning-playbook
title: Planning Playbook (Stories, Phases, Tasks, Features)
status: Adopted
owner: agent
updated: 2025-08-21

Purpose
- Define how we plan, document, and execute work so humans and LLM agents can query/extend consistently.

Structure at a glance
- dev/stories/<story-slug>/story.md — id: story:<slug>; phases/phase-XX-<slug>.md — id: phase:<story>/<order>-<slug>
- dev/tasks/ — one file per task; id: task:<area>/<theme>/<slug>
  - index.md — Ready Queue (≤ ~12), sorted by RICE desc, status=Ready with dor: true
  - _TEMPLATE.md — canonical task schema
- dev/features/<area>/feature-<slug>.md — specs/contracts; id: feature:<area>/<slug>
- dev/design/ — deep implementation notes
- dev/vision/ — longer-horizon direction
- dev/ops/ — deployment/runbooks
- dev/plans/ — dated plans consolidating near-term increments
- dev/cycles.md — lightweight weekly log and links; dev/cycles/ — dated reviews

IDs and metadata
- Story: story:<slug>
- Phase: phase:<story-slug>/<order>-<slug>
- Task: task:<area>/<theme>/<slug>
- Feature: feature:<area>/<slug>
- Prefer YAML-like frontmatter at the top of each markdown. Triple-dash fences are optional; grep-friendly keys are sufficient for now.

Task schema (see dev/tasks/_TEMPLATE.md)
- Keys: id, title, status, owner, rice, estimate, created, updated, dor, dod, dependencies, tags, story, phase, links, acceptance
- When a task is selected for a phase, set story and phase in the task frontmatter.

Ready Queue rules (dev/tasks/index.md)
- Only status: Ready and dor: true
- Max ~8–12 items
- Sorted by RICE desc
- Cycles select tasks from this queue

Stories and phases
- Stories hold the narrative and link to phases.
- Phases define demoable slices with acceptance and a demo checklist.
- Phases list selected tasks by ID; details live in task files.

cycles.md (lightweight)
- Active Story/Phase (IDs only), Selected Tasks table (IDs + ETA + owner), dependency table (IDs), demo checklist, decision/risk log, retro.

Query recipes (grep-friendly)
- Ready tasks by area: grep -R "^status: Ready" dev/tasks/ui
- Top candidates: grep -R "^rice:" dev/tasks | sort -nr -k2
- Tasks for a story: grep -R "^story: story:<slug>" dev/tasks
- Tasks for a phase: grep -R "^phase: phase:<story-slug>/" dev/tasks
- Features by area: grep -R "^id: feature:core-architecture/" dev/features

Maintenance
- When selecting a task into a phase, set story and phase.
- Keep indices up-to-date: dev/stories/index.md, dev/features/index.md, dev/tasks/index.md.
- Convert legacy docs to pointer stubs to avoid drift; later, delete them per cleanup schedule.
- Prefer small, demoable increments aligned to GUI acceptance.

Entry points
- README.md (root): see Backlog & Planning section linking to this playbook.
- CONTRIBUTING.md (root): contributor quickstart linking to this playbook.
- .github/PULL_REQUEST_TEMPLATE.md: DoR/DoD checklist and Related IDs.

References
- dev/stories/index.md
- dev/features/index.md
- dev/tasks/index.md
- dev/cycles.md
- dev/plans/
