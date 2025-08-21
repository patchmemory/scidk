# Tasks UI Polling (MVP)

id: ui:mvp:tasks-ui-polling
status: In progress
owner: agent
last_updated: 2025-08-21 09:45 local
related:
- README.md (Background Tasks section)
- dev/plan-next-increments-2025-08-21.md (Progress Log)

Objective
- Provide a simple polling pattern for background Tasks so the Files page (and others) can display progress and completion state for scan and commit tasks.

Endpoints
- POST /api/tasks { type: 'scan', path, recursive? } → { task_id }
- POST /api/tasks { type: 'commit', scan_id } → { task_id }
- GET /api/tasks/<id> → { id, type, status, progress, processed, total, scan_id?, error? }
- GET /api/tasks → list of recent tasks (sorted by started desc)

Polling Pattern (1–2s interval)
- Create task; store task_id.
- Poll GET /api/tasks/<task_id> every 1000–2000 ms.
- Stop polling when status ∈ { completed, error, canceled }.
- Update UI progress bar with value = (progress || processed/total || null) and show an indeterminate state when null.
- On completion with scan_id, navigate to the scan summary or refresh Files view.

Pseudocode (vanilla JS)
```
async function startScan(path, recursive){
  const resp = await fetch('/api/tasks', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ type:'scan', path, recursive }) });
  const { task_id } = await resp.json();
  pollTask(task_id);
}
async function pollTask(task_id){
  const timer = setInterval(async () => {
    const r = await fetch(`/api/tasks/${task_id}`);
    const t = await r.json();
    renderProgress(t.progress, t.processed, t.total);
    if (['completed','error','canceled'].includes(t.status)){
      clearInterval(timer);
      onTaskDone(t);
    }
  }, 1000);
}
```

UI Notes
- Show a Cancel button only when we add cooperative cancel; current backend does not yet support cancel.
- Consider a small Tasks drawer listing recently started tasks with badges by type.

Next Steps
- Wire this pattern into the Files page once the background-scan checkbox is added.
- Add cancel endpoint and max concurrent tasks enforcement per plan (SCIDK_MAX_BG_TASKS).
