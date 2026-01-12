# E2E and Neo4j Task Planning (Revised — Interpreter Terminology)

This plan aligns E2E testing and the Neo4j refactor with the Interpreter Management System and current API contracts.

## Story: E2E Testing & Neo4j Integration
- ID: story:e2e-testing
- Objective: Establish reliable E2E scaffolding (pytest + Playwright) to validate SciDK core flows and support Neo4j persistence refactor.

## Phases
1. Smoke E2E baseline: Validate core flows (Scan, Browse, Interpreters, Map) without Neo4j.
2. Neo4j refactor: Make Neo4j the live graph store (foundational).
3. Expanded E2E: Add Neo4j-specific tests, interpreter workflows, and negatives.

## Success Criteria
- Core MVP flows pass E2E in CI; Neo4j driver integration solid and tested.
- Interpreter registration and execution validated E2E.

## Tasks
- task:e2e:01-smoke-baseline — Playwright smoke E2E baseline (MVP flows). RICE 999. Status: Ready.
- task:e2e:02-neo4j-refactor — Neo4j as live graph store. RICE 998. Status: Ready.
- task:e2e:03-expanded-e2e — Neo4j-specific E2E + interpreter workflows + negatives. RICE 997. Status: Planned.

## Interpreter Terminology and APIs
- Use Interpreters (not Enrichers) consistently.
- Required endpoints: GET/POST /api/interpreters, GET /api/interpreters/<id>, POST /api/interpreters/<id>/test, POST /api/scans/<id>/interpret.

## E2E Notes
- Prefer BASE_URL injection; keep smoke tests fast (<5s/spec) and independent of external services.
- Add data-testid hooks for Settings, Interpreters, Map, Scan flows.

## References
- MVP_Architecture_Overview_REVISED.md
- SciDK_Interpreter_Management_System.md
