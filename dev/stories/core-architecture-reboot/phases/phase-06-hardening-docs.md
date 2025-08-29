id: phase:core-architecture-reboot/06-hardening-docs
story: story:core-architecture-reboot
order: 6
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: Hardening (timeouts, caps, structured errors), telemetry/metrics, and developer docs; tag v0.1.0
acceptance:
  - Directory listing P95 ≤ 120 ms on 200k+ files (warm cache) in a benchmark script
  - Caps/timeouts enforced with structured error responses
  - Metrics endpoint exposes scan throughput, browse latency P50/P95, and outbox lag
  - Quickstart docs enable fresh install to first crate in < 30 minutes
selected_tasks:
  - task:ops/mvp/metrics-and-logging
  - task:ops/mvp/docs-quickstart
links:
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
