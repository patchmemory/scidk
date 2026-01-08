Title: E2E foundation, contracts, and CI

Summary
- Implements Playwright E2E scaffold with smoke + core flow specs (browse, scan)
- Adds minimal API contracts for /api/scan, /api/scans/<id>/status, /api/directories
- Aligns Dev CLI timestamps to timezone-aware ISO8601
- Adds stable data-testid hooks to UI templates
- Wires CI for pytest and strict E2E smoke
- Updates docs/testing.md with quickstarts and CI notes

Related
- Story: story:e2e-testing
- Phase: 02–03
- Task(s):
  - task:e2e:02-playwright-scaffold (Done)
  - task:e2e:03-core-flows (partially addressed by initial specs; remaining flows in next branch)

Local verification
- Python tests: python -m pytest -q → green
- Playwright E2E: npm install && npx playwright install --with-deps && npm run e2e → green

CI
- GitHub Actions workflow runs:
  - Python tests (3.11)
  - E2E smoke (Node 18) — strict, SCIDK_PROVIDERS=local_fs

How to run locally
- API contracts: python -m pytest tests/contracts/test_api_contracts.py -q
- E2E: npm run e2e (uses e2e/global-setup.ts to boot the Flask server)

Risk assessment
- Low risk. Mostly additive tests/config/docs. UI changes limited to data-testid attributes.

Merge checklist
- [x] pytest green locally
- [x] E2E green locally
- [x] CI expected to pass (strict E2E)
- [x] task:e2e:02-playwright-scaffold marked Done with completed_at
- [ ] Reviewer sanity pass on docs/testing.md and CI workflow

Post-merge (follow-up branch)
- Expand Phase 03 core flows E2E and refine contracts as needed.
