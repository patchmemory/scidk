# Prompt 18.02: mature graph management in Knowledge

Implemented under the explicit approval in `scidk_prompt_18_02_b.txt`.
Branch: `design/knowledge-curation-20261029`; starting HEAD: `04a8e09`.
Implementation revision is recorded below after commit. All unrelated untracked
prompts, handoffs and user documents are preserved. Prompt 19 has not begun.

## Result

Knowledge now exposes first-class Entities & Labels, Properties, Relationships &
Links, Maps & saved views, and distinct Governed records navigation. The existing
Labels/Links templates, JavaScript, services and API operations are reused through
full-page internal navigation in the Prompt 16 shell. No iframe or replacement
entity browser was introduced. Human Research browsing no longer incorrectly
suggests an AI provider is required.

A named ordinary researcher with explicit development-connection grants can
browse the original schema/property editor, load actual node instances, inspect
incoming/outgoing relationships, edit and persist a property, select a related
entity, open that entity in the existing Cytoscape Maps workspace, view saved
maps, and return to the original entity inspector. The selection is re-fetched
under current authority. Scientific names replace element IDs as primary labels;
element IDs remain transient legacy lookup context.

The complete original-versus-integrated capability matrix, exact routes,
read/write analysis, provisioning instructions and remaining restrictions are in
[the integration architecture](../architecture/scidk-entity-management-integration.md).

## Authorization and preflight findings

The preflight demonstrated an ordinary authenticated user creating a label with
a foreign Origin and deleting shared schema without a management grant. That
probe used only disposable SQLite state. The user's subsequent approval
specifically authorized correcting this boundary.

`ManagementPolicyStore` reuses existing named users and audit infrastructure.
Permissions are `graph_management_read`, `graph_entity_write`, and
`graph_schema_write`, bound to the exact allowlisted development URI, username,
database and auth mode. There are no automatic grants or administrator bypass.
The existing APIs and graph client enforce fresh checks. Anonymous/no-auth,
header/token, foreign-origin/cross-site, disabled/locked, ungranted and revoked
requests are denied. Destructive shared schema/map/query deletion and schema-field
removal require schema-write authority and explicit confirmation. Imports use the
same service-side removal checks. Raw query execution remains denied.

Management grants do not supply Resource/evidence, Review, curation acceptance or
AI disclosure authority. The exact synthetic Dataset search adapter from Prompt
17 retains its original governed checks before the legacy API gate; other graph
searches require management authority.

## Browser evidence

Real production services, an isolated development app and a newly created
Neo4j 5.13.0 container were used. The graph contains only fictional specimens and
images with reciprocal relationship types. This is actual database interaction,
not HTML-only mocks or operational-data acceptance.

| Experience | Desktop 1440×900 | Laptop 1024×768 |
|---|---|---|
| Labels / property types | [Labels](gui-prompt18-02-candidates/management-labels-1440x900.png) | [Labels](gui-prompt18-02-candidates/management-labels-1024x768.png) |
| Instances / relationships | [Entities](gui-prompt18-02-candidates/management-entities-1440x900.png) | [Entities](gui-prompt18-02-candidates/management-entities-1024x768.png) |
| Related entity inspector | [Inspector](gui-prompt18-02-candidates/management-inspector-1440x900.png) | [Inspector](gui-prompt18-02-candidates/management-inspector-1024x768.png) |
| Existing Maps / saved view | [Maps](gui-prompt18-02-candidates/management-map-1440x900.png) | [Maps](gui-prompt18-02-candidates/management-map-1024x768.png) |
| Relationship discovery | [Links](gui-prompt18-02-candidates/management-relationships-1440x900.png) | [Links](gui-prompt18-02-candidates/management-relationships-1024x768.png) |

Candidates were visually inspected; human visual approval remains pending.
Approved baselines were not changed. Environment metadata is alongside images.
Maps' existing CDN dependencies are now pinned local assets with licenses,
upstream URLs and SHA-256 hashes, avoiding third-party network requests.

## Verification

Final backend regression: **676 passed, zero failures**, 212.82 seconds. Command:

```bash
PYTHON_DOTENV_DISABLED=1 SCIDK_CONCEPT_GRAPH_ENABLED=0 .venv/bin/python -m pytest \
  tests/security tests/knowledge_e2e tests/pipeline tests/test_dev_gui.py \
  tests/test_llm_provider_settings.py tests/test_auth.py -q -o addopts=''
```

The installed virtualenv is `/home/patch/PycharmProjects/scidk/.venv`.
Final GUI plus latest management security verification: **79 passed, zero
failures**, 181.00 seconds (63 GUI scenarios and 16 management security cases).
There were 25 existing Python AST deprecation warnings, no browser errors.

```bash
PYTHON_DOTENV_DISABLED=1 SCIDK_TEST_DISPOSABLE_NEO4J_URI=bolt://127.0.0.1:32768 \
  .venv/bin/python -m pytest tests/security/test_graph_management.py tests/gui \
  -q -o addopts='' --gui-record-candidates \
  --gui-artifacts /tmp/scidk-1802-browser-final
```

This includes Files/rclone fixtures, Dataset inspection, annotations, Resources
schema/mapping, Knowledge Graph/Sketch, Review, Ask, NIH DMS/sharing export and
management denial. The final management browser scenarios also load a saved map.
Screenshot candidates in this report come from this final passing run.
Earlier focused validation:
36 passed across management security and Pipeline schema tests. An initial broad
backend run had 671 passes and two old anonymous Canvas assumptions; those tests
now explicitly provision a named admin (required by Pipeline) with a management
read grant while preserving source-cleanup/isolation assertions.

The first complete GUI run had 62 passes and one Sketch placement failure because
the second click was below the viewport after navigation increased page height.
The test now scrolls the actual canvas into view before each click. Follow-up
verification passed both management viewports and Sketch placement: 3 passed.
Browser work also corrected an obsolete singleton Cytoscape initializer and a
race between deep-linked entity loading and asynchronous tab initialization.

A sandboxed backend run stopped at 163 passes with two loopback-server setup
errors (`PermissionError`); the same suite is rerun with local sockets permitted.
No paid provider calls were made; provider transport tests use local fake servers.

## Remaining limitations

- Advanced bulk/background graph execution, transfers, imports and enrichment
  remain denied until worker authority and every source/destination are scoped.
  External/API-source previews and arbitrary WHERE/Cypher are unavailable.
  Existing synchronous property edits and shared definition edits are supported.
- Saved maps and query definitions retain their existing shared-store behavior;
  private Canvas draft ownership remains distinct. This is not per-tenant graph
  catalog isolation.
- Some advanced legacy controls remain visible and return a refusal. The raw
  Maps Run button is disabled. No generic graph creation API was added.
- Operational research data/configuration was neither accessed nor modified in
  this implementation. The earlier Prompt 18 provenance/source-binding blockers
  remain. No operational records were assigned fabricated Resource/evidence or
  accepted-assertion status. Only the disposable synthetic graph was edited.
- This report does not certify every historical no-auth test or advanced legacy
  endpoint as compatible with the new explicit-grant contract.

The disposable test container is removed after verification; existing services
are left unchanged. Prompt 19 is out of scope.
