# Demo-Ready Noon Roadmap

**Date:** 2026-11-03  
**Goal:** Finish demo-visible development by noon; reserve the afternoon for data preparation, logistics and rehearsal.

## Definition of done at noon

The demo tells one coherent story:

```
Overview → shared Chat workbench → Datasets/Browse → Knowledge → Review
```

Resources explains the future intake model honestly without requiring a live external plugin. No new external integration, scheduler, provider, ontology change, or broad backend migration is required for the noon demo cutoff.

## 09:00–09:20 — Scope lock and baseline

- Confirm branch head and clean working tree.
- Confirm :5010 only; do not touch :5001.
- List the intended demo routes and record existing known failures separately:
  - stale visual baselines;
  - unrelated auth/Neo4j failures;
  - no configured AI provider;
  - no installed external source plugins.
- Do not begin SharePoint, iLab, PubMed, PubChem or EDA implementation in this window.

**Exit:** one explicit checklist of the demo routes and truthful capability states.

## 09:20–10:05 — Shared Chat workbench shell

Build a reusable inset Chat workbench accessible from Overview and Review.

- Conversation pane, input, compact search/query area, Advanced grounded query tools.
- Recent-conversation rail has a truthful empty/unavailable state unless real history is configured.
- Close returns visually to the launching page; full-page Chat deep links remain valid.
- Prefills remain visible and unsent.
- No provider/network calls, persistence, fabricated answers or fake history.

**Exit:** Overview and Review launch the same component; direct Chat route remains usable.

## 10:05–10:35 — Overview and Review polish

- Overview is a compact scientific starting point, not a second Chat product.
- Review is the five-task workspace: Curate, Annotate, Evaluate, Enrich, Publish.
- Normalize card density, headings, controls and page width.
- Make direct actions and “Discuss in Chat” paths legible and consistent.

**Exit:** a visitor can explain the difference between Overview, Review and Chat in one sentence each.

## 10:35–11:15 — Resources roadmap mockup

Make Resources communicate the intended architecture without claiming unbuilt integrations.

- Ecosystem: services, storage, inventory, interpretation.
- Sources: visibly offer built-in table/file import as available; configured-source state remains factual.
- Plugins: show capability classes and true installed/built-in/planned status.
- Runs: show manual/history state when no scheduler exists.
- Keep Settings as the home of credentials and sensitive profiles.

**Exit:** the page can support a spoken walkthrough of Source plugin → Source instance → mapping → run, while showing no false CSV/SharePoint/PubMed availability.

## 11:15–11:40 — Focused test and browser verification

- Add/update focused tests only for changed UX behavior.
- Chromium verification at 1440px and 1024px:
  - Overview launch;
  - Review task and Chat prefill;
  - Chat close/direct links/empty history;
  - Resources tab structure/statuses;
  - no console/page errors on the walkthrough routes.
- Save structural screenshots under one git-ignored demo folder.

**Exit:** tests pass for the changed areas; screenshots show the intended walkthrough.

## 11:40–12:00 — Freeze and handoff

- Commit local changes; do not push until the browser result is accepted.
- Write a short demo runbook:
  1. Overview;
  2. Browse/Collection;
  3. Knowledge;
  4. Review;
  5. Chat;
  6. Resources roadmap.
- Record intentionally deferred work:
  - SharePoint activation;
  - iLab Pipeline adapter;
  - PubMed/PubChem connectors;
  - EDA Pipeline adapter;
  - generalized plugin acceptance suite;
  - API/documentation portal;
  - visual baseline regeneration.

## Afternoon: data and logistics, not feature expansion

Once the noon cutoff is met:

- prepare the selected demo Dataset and Collection;
- validate graph/entity examples and screenshots;
- rehearse the narrative;
- verify the environment and credentials needed for the symposium;
- decide which Source/Plugin work enters the next development block.

## Next development block

1. Built-in table-file Source UI activation.
2. SharePoint Intake source against a local export, then rclone profile.
3. iLab adapter over TabularFilePlugin.
4. Reusable source-plugin acceptance suite.
5. EDA, PubMed, PubChem based on that proven pattern.
