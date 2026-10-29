# SciDK vision v1.1 — implementation scope addendum

**Date:** 2026-10-29  
**Applies to:** `docs/vision/scidk-vision-v1.1.md`  
**Status:** Proposed append-only addendum; retain the existing vision text.

## Integrated GUI commitment

The redesigned interface is an active target for the NCI 2026 development build. The primary navigation is **Overview → Files & Datasets → Resources → Knowledge → Review → Settings**.

Overview centers accepted-knowledge discovery and Ask SciDK. Files & Datasets provides distinct Files and Datasets tabs, an expandable metadata/annotations/provenance inspector, administrator-managed `+ Drive` discovery, and selected-dataset **Prepare for Sharing**. Resources preserves the existing Source → Schema → Mapping builder. Knowledge exposes Research/Ontology/System domains and Graph/Entities/Sketch views, reusing Cytoscape, Entities, and Canvas. Review provides human decisions, evidence, and a context-aware assistant. Settings governs providers, plugins, access, and operations.

Sketch is domain-aware and remains a private draft until promoted through governed curation. A minimal bounded enrichment task may investigate missing knowledge and submit cited proposals, but agents cannot accept or materialize them.

Existing workflows, routes, saved sessions, annotation data, and mapping configurations must be preserved. Implement incrementally in an isolated development branch, with feature flags and release gates.

## Stage 6 evidence and boundaries

Codex reported Stage 6 at commit `0896c5a`, 666 passed, 0 failed, 1 skipped. It reported a fix preventing Overview from disclosing pending/rejected facts despite Review grants. The existing NIH DMS exporter reportedly summarizes the whole graph and requires a dataset-scoped authorized adapter. Live Neo4j materialization/recovery remains unverified. These are implementation findings, not claims of production readiness.
