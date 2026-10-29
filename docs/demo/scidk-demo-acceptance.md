# Prompt 17 demonstration acceptance

Environment: disposable local SQLite/settings and memory application graph, actual
Ledger/ReviewService and persisted **simulated** materialization using the tested
FakeGraph. Production factory, actual GUI routes and actual loopback HTTP provider
were exercised. No operational graph, institutional records or paid provider.
Implementation revision and final test counts are recorded in
`docs/design/gui-prompt17-report.md`.

| Step | Status | Evidence and limit |
|---|---|---|
| Authenticated integrated launcher | PASS (disposable) | Existing `dev_gui` plus explicit `dev_integrated_demo:seed_reviewed`/`:configure` hooks. Production-factory browser tests use named cookies; backend verifies restart without reseeding. Runbook provides interactive CLI/login command. |
| Provider-independent ordinary-user browsing | PASS | `test_prompt17.py` and `test_prompt17_demo.py`: explicit purpose/Resource/evidence grants, accepted/applied records and independent legacy record grants; missing grants deny. |
| Files → Dataset metadata/provenance | PARTIAL | Production Files page browses confined real synthetic file directory; governed demo collection search returns actual ledger-backed Dataset. Metadata/provenance and Knowledge links work. This is explicit fixture onboarding, not automatic recognition/ingestion of scientific images. |
| Research Graph / Entities / expansion | PASS (synthetic) | Three accepted/applied nodes and two membership edges, real support serializer; named user with no provider. Dataset link opens selected inspector. |
| Legacy/unreviewed | PARTIAL | Bounded immutable synthetic source snapshot, stable source-derived IDs, actual ledger evidence and explicit record/evidence grants. Honest unreviewed/unverified state, no accepted support. No operational legacy Neo4j adapter enabled. |
| Sketch and saved sessions | PASS in isolated regression | Existing private visual node/edge, save/reopen and reference-revocation tests retained. Integrated candidates capture Sketch; no scientific graph commit. |
| Review queue/evidence/preview/confirm | PASS (synthetic) | Real ReviewService, explicit reviewer grant plus human read authority and source/evidence checks. Browser rejects the pending synthetic name revision with confirmation; backend verifies stale replay, revocation and pending application status. |
| Materialization | PASS (simulation only) | Explicit seed command makes 12 actual human decisions and uses real outbox/materializer to produce 12 applied receipts for the simulation target. Persistent graph state restarts. Live disposable Neo4j is UNVERIFIED. New UI decisions are not automatically applied. |
| Overview without manual node IDs | PASS (loopback fake) | Actual lexical lookup, real provider HTTP adapter, consent and grounded source links in production-factory browser test. Fake interpretation is constant, explicitly synthetic, not scientific reasoning. |
| Real Parley smoke | BLOCKED / unverified | Operator-only one-request procedure with exact approval, synthetic context, consent and cost guardrails in runbook. No paid call made. User-reported model discovery is not approval or this verification. |
| Dataset-scoped DMS draft and package | PASS (synthetic) | Actual authorized Dataset membership, two supported files, Markdown and ZIP through real sharing endpoint without AI provider. No whole-graph fallback. Bash is executed against synthetic files and staged bytes compared by backend tests. |
| Checksums / Windows | PARTIAL | Manifest/provenance supplied. Unchanged fixture catalog has no sha256 field, so expected hashes are not fabricated. PowerShell inspected statically; execution on Windows unverified. |
| Resources Source → Schema → Mapping | PARTIAL | Existing routes and actual Sources page retained; pipeline regression exercises CSV schema/mapping independently. The synthetic seed Resource is not a runnable importer or a full Resources-to-ledger ingestion adapter. |
| Annotations / Interpreters | PASS in existing isolated regression | Existing routes/drawer retained and exercised by browser/pipeline fixtures; no new annotation store or interpretation engine. Scientific acquisition interpretation in this integrated text-artifact demo is UNVERIFIED. |
| Visual system / browser errors | PASS for captured workflow, operator review pending | Candidate captures at 1440×900 and 1024×768, overflow assertions and strict browser error collection. No baselines updated/approved. Human review of candidates and live behavior remains required. |
| Security regression / secret handling | See final report | Separate human/AI identities; purpose/Resource/evidence/property/classification/reviewer checks; origin/header/anonymous/noauth/locked/revocation tests. Secret remains untracked and is now narrowly ignored, without reading it. |
| Repeat / fallback | PASS (synthetic restart), operator rehearsal pending | Configure refuses absent seed state; seeding refuses reused state. Runbook gives safe restart, separate port, shutdown and preserved System-only fallback. No existing 5001/5002 process was restarted. |

Release recommendation: the explicitly synthetic integrated vertical slice is
demonstrable subject to operator rehearsal and screenshot review. Do not describe
it as operational graph integration, a complete multimodal ontology, automatic
scientific ingestion, verified Windows execution, institutional compliance or a
successful live Parley test. The post-demo Controlled Burn has not begun.
