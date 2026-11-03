# Source Plugin Family Roadmap

Purpose: post-demo ingestion architecture. This is a roadmap, not a claim that these integrations are installed or runnable today.

## Product principle

> Any table in; one mapping and validation path through SciDK.

A Source is a reproducible configured intake boundary: a file, folder, query, API request, package, or remote location. A plugin capability describes how to inspect and read it.

## Shared lifecycle

Plugin capability → optional connection/profile → configured Source → inspect/preview → schema or mapping review → FAIR/QC/dry run → explicit run → structured provenance and history.

The Pipeline owns mapping, writes, dry-run reporting, scheduling, and history. Source plugins must not write directly to the graph.

## Source families

| Family | Examples | Inspection/output shape | Mapping path |
| --- | --- | --- | --- |
| Tabular | CSV, TSV, XLSX, Parquet, Feather, SQL tables/views/queries | Typed columns, bounded sample, row stream | Column-to-schema mapping |
| Record/API | REST, GraphQL, PubMed/MeSH, PubChem | Normalized records, pagination/rate information | Row-like mapping or API normalization |
| Scientific artifact | NC3Rs EDA, instrument packages, RDF/OWL | Design/schema/entities/graph proposal | Proposal review, not forced columns |
| Research package | RO-Crate | JSON-LD manifest, files, checksums, entities, provenance | Inventory/provenance proposal and optional entity mapping |
| Enrichment/lookup | Identifiers, pathways, controlled vocabularies | Proposed annotations/links | Explicit enrichment review |
| Export/publish | RO-Crate, CSV extract, RDF export | Portable package | Downstream of Collection or approved result |

## Tabular foundation

The built-in TabularFilePlugin is the first canonical Source capability. It should handle local or mounted CSV, TSV and XLSX; later Parquet and Feather after dependency/type checks; database results through read-only SQL/ODBC adapters; and remote files through approved storage profiles. Every adapter emits a neutral typed row stream for the same mapping, FAIR, dry-run, provenance, and Runs experience.

### Template packs

Scientific meaning belongs in versioned Source templates, not in the file reader. Initial candidates are AIPT SharePoint Intake CSV, iLab Equipment Export CSV, iLab Services Export CSV, iLab PI Directory CSV, and Facility Inventory CSV.

A template carries expected/header aliases, a mapping starter, transforms, relationship rules, FAIR/QC and controlled-vocabulary checks, documentation/version, and optional example headers. Creating a Source copies the selected configuration; later edits never mutate the template or another Source. A future SharePoint connector refreshes the same Source model remotely.

## REST/API sources

REST is a transport, not automatically a tabular model. An API source must declare profile/secret boundaries, bounded discovery and pagination, rate limits/retry guidance, normalized records, stable identifiers and retrieval provenance, a read-only access test, and any source-specific transforms.

PubMed/MeSH and PubChem are future API-backed Sources. Saved Source configuration records endpoint, query or identifiers, retrieval range, profile, and snapshot/fingerprint policy.

## Scientific artifacts

### EDA

The existing EDA parser is a starting point. An EDA Source should inspect the package, extract a design/schema/relationship proposal, validate it, show a reviewable proposal, dry run with zero writes, require explicit approval before managed schema or graph writes, and record provenance/history.

### RO-Crate

An RO-Crate Source should read ro-crate-metadata.json and payload; validate JSON-LD, crate profile/version, referenced files and supplied checksums; inspect Dataset, Person, Organization, Instrument, license and provenance entities; distinguish inventory/provenance from managed-schema changes; and offer Inspect-only, Inventory, Mapping Preview, and Explicit Import modes.

SciDK's existing RO-Crate export/build path makes a reader strategically valuable for round-trip research exchange.

## Plugin acceptance suite

Every source-capable plugin must prove manifest validity; clear redacted configuration errors; fixture-backed find/access/fetch/transform tests; safe malformed-input/missing-profile/timeout/credential-failure behavior; preview/mapping compatibility; zero-write FAIR/dry run; provenance/history on permitted run; and capability-gated scheduling/retry only where the plugin and infrastructure support it.

## Delivery order

1. Finish and push the accepted demo UI commit.
2. Canonical built-in tabular Source plus template packs.
3. SharePoint Intake with local export, then configured rclone/profile.
4. iLab adapter over the tabular Source contract.
5. Plugin acceptance harness.
6. RO-Crate reader and EDA proposal workflow.
7. PubMed/MeSH and PubChem API sources.