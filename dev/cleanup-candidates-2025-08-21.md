# Cleanup Candidates — 2025-08-21

Purpose
- Identify legacy folders/files that do not fit the standardized planning schema and are safe to delete in a future sweep.
- Preserve clear rationale and canonical replacements so we can backtrack if needed.

Deletion policy
- Do not delete immediately if you KNOW external links still point here. If so, please first fix the old pointer, then delete.
- When deleting, use a commit message like: "dev(cleanup): remove legacy dev/*/mvp docs now superseded by features/tasks; see dev/cleanup-candidates-2025-08-21.md for mapping and rationale."

Canonical schema (reference)
- Keep only these top-level categories under dev/: stories/, tasks/, features/, design/, vision/, ops/, plans/, cycles.md, cycles/.

Candidates (folders)
1) dev/core-architecture/ (legacy docs under mvp)
   - Reason: Specs now live under dev/features/core-architecture and design notes under dev/design/graph/.
   - Replacement: see dev/features/core-architecture/* and dev/ops/deployment-neo4j.md.
   - Action: delete the dev/core-architecture/ tree after a deprecation window if no active links remain.

2) dev/interpreters/ (legacy mvp docs)
   - Reason: Specs live under dev/features/interpreters/; tasks under dev/tasks/interpreters/.
   - Replacement: dev/features/interpreters/* and dev/tasks/interpreters/mvp/task-ipynb-interpreter.md.
   - Action: delete dev/interpreters/ after deprecation window.

3) dev/ui/ (legacy mvp docs)
   - Reason: Features under dev/features/ui/. A remaining doc (dev/ui/mvp/tasks-ui-polling.md) duplicates task notes; canonical sources are dev/tasks/ui/mvp/task-tasks-ui-polling.md and dev/plans/plan-2025-08-21.md.
   - Replacement: dev/features/ui/* and the task file.
   - Action: convert dev/ui/mvp/tasks-ui-polling.md to a pointer stub (done) and delete dev/ui/ after deprecation window.

4) dev/plugins/ (legacy mvp docs)
   - Reason: Plugin loader now specified at dev/features/plugins/feature-plugin-loader.md.
   - Replacement: dev/features/plugins/*
   - Action: delete dev/plugins/ after deprecation window.

Candidates (files at dev/ root)
- dev/deployment.md → Pointer stub to dev/ops/deployment-neo4j.md (safe to delete after deprecation window).
- dev/cycle-review-2025-08-18.md → Pointer to dev/cycles/2025-08-18-review.md (safe to delete later).
- dev/plan-next-increments-2025-08-21.md → Pointer to dev/plans/plan-2025-08-21.md (safe to delete later).
- dev/core-architecture.md → Pointer to dev/vision/core_architecture.md (safe to delete later).
- dev/interpreters.md → Pointer to dev/vision/interpreters.md (safe to delete later).
- dev/plugins.md → Pointer to dev/vision/plugins.md (safe to delete later).
- dev/stories/story-chat-history-storage.md → Pointer to dev/stories/chat-history-storage/story.md (safe to delete later).

Why safe to delete
- All content has canonical replacements under stories/, tasks/, features/, design/, vision/, ops/, plans/.
- dev/cycles.md and indices have been updated to link to canonical locations.

Backtrack plan
- If a deletion causes trouble, recover via git by checking this manifest and restoring the specific file from the previous commit.
- Keep this file updated on each cleanup pass (create a new dated manifest per pass).
