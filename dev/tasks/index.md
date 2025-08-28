# Ready Queue (top by RICE)

id | title | area | status | RICE | estimate | tags
---|---|---|---|---:|---|---
task:providers/mvp/rclone-provider | Feature-flagged RcloneProvider (subprocess-based) | providers | Ready | 4.0 | 2–3d | [rclone, browse, scan]
task:providers/mvp/rclone-docs-and-readme | Rclone Quickstart Docs + README-ready Snippet | providers | Ready | 3.6 | 0.5–1d | [rclone, docs]
task:providers/mvp/rclone-mount-manager-mvp | Settings → Rclone Mount Manager (MVP) | providers | Ready | 3.9 | 1–2d | [rclone, mounts, ui]
task:providers/mvp/rclone-browse-options | Rclone browse options (recursive, max-depth, fast-list) | providers | Ready | 3.4 | 0.5–1d | [rclone, browse]
task:providers/mvp/rclone-host-and-ui-remote | Host/provider tagging + Rclone Files UI (Remote + relative path) | providers | Ready | 3.7 | 0.5–1d | [rclone, ui, graph]
task:ui/mvp/tasks-ui-polling | Files page polling for background Tasks | ui | Ready | 3.8 | 0.5–1d | [ui, tasks]
task:ui/mvp/home-search-ui | Home search UI (quick filter over scanned sources) | ui | Ready | 3.8 | 0.5–1d | [ui, home, search]
task:core-architecture/mvp/neo4j-adapter-prep | GraphAdapter prep for Neo4j backend | core-architecture | Ready | 3.3 | 0.5–1d | [graph, neo4j]
task:ops/mvp/error-toasts | Error toasts for browse/scan failures | ops | Ready | 1.3 | 0.25–0.5d | [ux, errors]

```yaml
ready_queue:
  - id: task:providers/mvp/rclone-provider
    rice: 4.0
  - id: task:providers/mvp/rclone-mount-manager-mvp
    rice: 3.9
  - id: task:ui/mvp/tasks-ui-polling
    rice: 3.8
  - id: task:ui/mvp/home-search-ui
    rice: 3.8
  - id: task:providers/mvp/rclone-docs-and-readme
    rice: 3.6
  - id: task:providers/mvp/rclone-host-and-ui-remote
    rice: 3.7
  - id: task:providers/mvp/rclone-browse-options
    rice: 3.4
  - id: task:core-architecture/mvp/neo4j-adapter-prep
    rice: 3.3
  - id: task:ops/mvp/error-toasts
    rice: 1.3
```
