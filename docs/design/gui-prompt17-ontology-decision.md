# Prompt 17 integration catalog decision

Status: **APPROVED for the disposable synthetic catalog exception**, 2026-10-29.
The operator selected “Approve the disposable synthetic catalog exception” in
response to the explicit decision question. Production reconciliation remains
blocked; this approval does not cover schema changes or operational data.

The approved human authorization contract does not approve ontology changes.
`scidk_prompt_17_01.txt` explicitly says not to alter ontology contracts and to
report additional material ontology-policy conflicts before proceeding.

## Reproduced mismatch

Read-only construction of `Ontology.from_yaml_paths` over
`scidk/labels/builtin/*.yaml` reports exactly `ImagingDataset`,
`InstrumentRecord`, and `Sample`. It does not declare `Dataset`, `File`, or
`FileSet`. ImagingDataset declares relationships to FileSet, Study and File, but
those references are not complete definitions of their target labels.

`scidk/services/dataset_sharing.py` requires accepted/applied `Dataset` existence,
direct `CONTAINS` relationships and `File` existence/property support. It cannot
export an ImagingDataset by relabeling it. The existing
`tests/fixtures/knowledge_curation/catalog.json` defines Person, Project and
SyntheticWorkOrder, not this membership model. The `datasets` fixture in
`tests/knowledge_e2e/test_prompt12.py` explicitly extends that catalog with a
fixture-only Dataset/File/CONTAINS model. The Prompt 15 reconciliation report
already records operational reconciliation as unresolved.

No operational SQLite label catalog or graph was opened to find an alternative.
No ontology was changed, acceptance inferred, or seed operation performed. A
legacy collection route's graph labels are not an authoritative ledger catalog.

## Recommended narrow decision

Approve promoting the **unchanged existing Prompt 12 fixture-only**
Dataset/File/CONTAINS definitions to a reusable, explicitly synthetic demo catalog
artifact, alongside the existing synthetic Person/Project catalog. Use it only in
fresh disposable state, clearly labeled simulation, never as an operational
ontology migration. Keep its existing vocabulary unchanged; do not silently add
modality/study properties or equate Dataset with ImagingDataset. Imaging examples
may be identified in permitted synthetic descriptions/file names, while any
missing structured scientific metadata remains explicitly PARTIAL.

Under that decision, assemble the actual Ledger, ReviewService and current-support
readers, make explicit synthetic reviewer decisions and apply through the tested
fake graph writer. Do not fabricate receipts. It remains simulated application,
not a live Neo4j verification. This narrow catalog exception would unblock
Dataset-scoped sharing in the integrated demo without changing production schema.

Alternatively, supply an approved, complete, read-only catalog snapshot covering
the required labels/properties and endpoint relationships. Any proposed bridge
between ImagingDataset/FileSet and Dataset/CONTAINS needs its own reviewed identity
and membership semantics; it is outside this narrow remedy.

Following approval, the unchanged Dataset/File/CONTAINS definitions were extracted
to `tests/fixtures/knowledge_curation/dataset_catalog.json` and are shared by the
existing Prompt 12 fixture and the new disposable integrated hook. The original
bundled YAML and base synthetic catalog were not changed. The integrated workflow
uses fictional text files and synthetic citation metadata; structured multimodal
catalog completeness and operational legacy browsing remain unverified.
