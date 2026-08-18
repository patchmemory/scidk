# Branching and CI Policy

Goal: Keep the development flow simple and reliable by working on one active branch at a time and relying on CI to validate changes before merge.

## Principles
- One active feature branch at a time per contributor.
- Open a Pull Request early and keep it small and focused.
- Let CI be the gate: do not merge locally; wait for required checks to pass.
- Prefer incremental PRs (fast review, fast CI) over large multi‑day PRs.
- If you must work on a second branch, document the reason in the PR description and link to the primary branch/PR.

## Recommended Flow
1) Create a branch from the default base (main):
   - `git switch -c chore/<short-topic>`
2) Push and open a PR as soon as there is a coherent change:
   - `git push -u origin HEAD`
3) Keep commits small; push frequently. Let CI run.
4) If CI fails, fix forward on the same branch; avoid force‑push unless rebasing noise.
5) Rebase/update with main when green to reduce drift:
   - `git fetch origin && git rebase origin/main`
6) Merge via the PR when required checks pass.

## PR Checklist
- [ ] The PR covers a single topic; scope is clear in the title/description.
- [ ] Linked story/task and acceptance criteria listed.
- [ ] Tests added/updated; CI is green or expected failures are explained.
- [ ] Docs updated (README or docs/*) if behavior or workflow changed.
- [ ] Justification added if working on multiple branches concurrently.

## CI Expectations
- Unit tests and smoke checks run on every PR.
- E2E smoke (where applicable) runs within a few minutes (<5s/spec target).
- Required checks must be green before merge.
- Dev submodule freshness: PRs to main must keep dev/ submodule at the latest commit of its configured branch (see .gitmodules). A CI check enforces this, and main auto-syncs dev/ after merge.

## Tips
- Use `python -m dev.cli ready-queue` to confirm current priorities.
- Avoid local merges between feature branches; rebase onto main instead.
- If a PR is taking too long, split it into smaller, independently shippable parts.
