id: task:<area>/<theme>/<slug>
title: <Short actionable title>
status: Ready | In progress | Blocked | Done | Deferred | Dropped
owner: <name>
rice: <number>
estimate: <e.g., 0.5d>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
dor: true | false
dod:
  - tests
  - docs
  - demo_steps
  - telemetry
dependencies: [task:..., task:...]
tags: [<keywords>]
story: story:<slug>
phase: phase:<story-slug>/<order>-<slug>
links:
  cycles: [dev/cycles.md]
  plan: []
  story: []
  phase: []
acceptance:
  - <criterion 1>
  - <criterion 2>

Notes
- Freeform notes and design details go here outside the frontmatter.
