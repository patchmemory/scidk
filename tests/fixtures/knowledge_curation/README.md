# Offline knowledge-curation demonstration

All records are synthetic planning/identity metadata. They contain no actual
investigators, measurements, acquisitions, experimental results or credentials.
`intake.csv` matches the existing SharePoint reference mapping's CACProtocol,
ShortDescription, RecordSource and PI Archived columns. RecordID and Disease
are retained source fields, not new operational mapping definitions.

`catalog.json` is an explicitly synthetic, isolated Person/Project/PI_OF catalog
plus the previously approved SyntheticWorkOrder alignment example. It is not
installed or reconciled into the operational ontology. `corroboration.json` is
a separate, synthetic personnel-check source with its own derivation root.

From the isolated development worktree, with the existing project environment:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e -v -o addopts=''
```

For only the core source-to-query narrative:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e/test_vertical_slice.py::test_mapping_human_review_and_agent_explanation -v -o addopts=''
```

The eight acceptance tests assemble existing services with temporary SQLite,
synthetic users/capabilities, named-human session review and the existing fake
transactional graph adapter. They exercise the real `MappingEngine` with the
unmodified `aipt_intake_mapping.json` and SharePoint transforms. The tiny test
adapter consumes resolved declarations; it does not copy mapping/transform logic.
It uses mapped CAC protocol identity within the Resource, and upstream RecordID
plus role for a name-only PI. No global name/email merge is authorized. Two rows
share a project and display name but retain distinct source-scoped PI references.

The narrative proposes separate existence, property and relationship assertions,
previews/reviews via real human HTTP endpoints, applies accepted operations via
the authorized internal materialization service, then queries through shared
agent handlers. Other tests cover recovery/replay, evidence/conflicts/supersession,
two principals, HTTP/chat/host-bound MCP parity, high/unknown classifications,
source/evidence/property/destination denials, System freshness, Ontology blockers,
proposed MONDO alignment and the existing human DMS exporter boundary.

The DMS test uses only synthetic accepted identity metadata and **zero scientific
files**. Its whole-graph summary is not a selected-dataset export. Existing NIH
DMS unit tests separately exercise synthetic format/volume fixtures. No real
provider, browser, SharePoint service or Neo4j is needed for this demonstration.
The optional real Neo4j test is separate and requires explicit disposable test
configuration; a URI or localhost alone is never sufficient.

These commands do not enable production flags, migrate production stores or
prove a production deployment. Existing curation/knowledge flags stay off by
default. Operational catalogs, deployment wiring, source/evidence grants and any
GUI presentation remain separate work. See the Stage 6 report for readiness limits.
