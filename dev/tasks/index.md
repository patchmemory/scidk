# Ready Queue (top by RICE)

id | title | area | status | RICE | estimate | tags
---|---|---|---|---:|---|---
task:core-architecture/mvp/rclone-scan-ingest | rclone lsjson scan and batch ingest into SQLite | core-architecture | Ready | 4.3 | 2d | [rclone, discovery, ingest]
task:core-architecture/mvp/sqlite-path-index | SQLite path-index schema and migrations (WAL enabled) | core-architecture | Ready | 4.2 | 1–2d | [sqlite, schema, performance]
task:ui/mvp/browse-api-and-pagination | Browse API with parent_path listing and pagination | ui | Ready | 4.0 | 1–2d | [ui, api, browse]
task:research-objects/mvp/ro-crate-referenced | Referenced RO-Crate generation from selection | research-objects | Ready | 4.1 | 1–2d | [ro-crate, metadata]
task:ops/mvp/rclone-health-check | /diag/rclone endpoint (version + remotes or clear error) | ops | Ready | 3.5 | 0.5–1d | [ops, rclone, health]

```yaml
ready_queue:
  - id: task:core-architecture/mvp/rclone-scan-ingest
    rice: 4.3
  - id: task:core-architecture/mvp/sqlite-path-index
    rice: 4.2
  - id: task:research-objects/mvp/ro-crate-referenced
    rice: 4.1
  - id: task:ui/mvp/browse-api-and-pagination
    rice: 4.0
  - id: task:ops/mvp/rclone-health-check
    rice: 3.5
```
