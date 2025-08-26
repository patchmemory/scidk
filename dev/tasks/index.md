---
status: Draft
---

# Ready Queue (top by RICE)

id | title | area | status | RICE | estimate | tags
---|---|---|---|---:|---|---
task:providers/mvp/rclone-provider | Feature-flagged RcloneProvider (subprocess-based) | providers | Ready | 4.0 | 2–3d | [rclone, browse, scan]
task:ui/mvp/tasks-ui-polling | Files page polling for background Tasks | ui | Ready | 3.8 | 0.5–1d | [ui, tasks]
task:ui/mvp/home-search-ui | Home search UI (quick filter over scanned sources) | ui | Ready | 3.8 | 0.5–1d | [ui, home, search]
task:core-architecture/mvp/neo4j-adapter-prep | GraphAdapter prep for Neo4j backend | core-architecture | Ready | 3.3 | 0.5–1d | [graph, neo4j]
task:ops/mvp/error-toasts | Error toasts for browse/scan failures | ops | Ready | 1.3 | 0.25–0.5d | [ux, errors]

```yaml
ready_queue:
  - id: task:providers/mvp/rclone-provider
    rice: 4.0
  - id: task:ui/mvp/tasks-ui-polling
    rice: 3.8
  - id: task:ui/mvp/home-search-ui
    rice: 3.8
  - id: task:core-architecture/mvp/neo4j-adapter-prep
    rice: 3.3
  - id: task:ops/mvp/error-toasts
    rice: 1.3
```