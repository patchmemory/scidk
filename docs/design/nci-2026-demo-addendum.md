# NCI 2026 demo plan — GUI scope and acceptance addendum

**Date:** 2026-10-29  
**Applies to:** `docs/demo/nci-2026-demo-plan.md`

The **redesigned GUI is in scope for the NCI development build**. The demonstration sequence is a scientific workflow, not a literal navigation order:

**Discover → Structure → Connect → Curate → Prepare to Share**.

### Required live demonstration path

1. **Files:** Open an authorized connected drive in the preserved file browser; demonstrate discovery and dataset recognition.
2. **Datasets:** Select a recognized dataset; open the expandable metadata inspector, inspect raw scientific metadata, annotations, provenance, and contributing files.
3. **Knowledge:** Explore accepted dataset-to-study/PI/modality links using existing Cytoscape and Entities; optionally open a Sketch to propose a missing connection.
4. **Review / Overview:** Demonstrate human review of a cited candidate, then ask Overview about currently supported accepted facts; show that the Review assistant can investigate without approving.
5. **Prepare for Sharing:** Export a **dataset-scoped, authorized NIH DMS Plan draft**. Show which fields came from SciDK and which require investigator input. Do not claim automatic compliance.

### Mandatory acceptance checks

- [ ] Redesigned six-destination navigation works, with legacy deep links preserved.
- [ ] File browser, Annotations, Resources builder, Entities, Cytoscape, and Canvas remain functional.
- [ ] Metadata inspector docks/expands without losing selected drive, file, dataset, or tab.
- [ ] Overview excludes pending/rejected/superseded unsupported facts even for reviewers.
- [ ] Two synthetic datasets produce distinct DMS drafts; no unrelated or restricted graph records appear.
- [ ] Review decisions require authenticated human authority; agent tools never accept claims.
- [ ] Demo-user permissions, disclosure, and provider destination approvals are tested.
- [ ] A fallback build or recording is prepared; production graph writes remain disabled pending disposable Neo4j verification.

Docking, MeSH/PubMed, pathways, and broader enrichment remain stretch features unless independently stable.
