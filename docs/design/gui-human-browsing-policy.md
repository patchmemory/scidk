# Human research browsing and review: proposed authorization decision

Status: **APPROVED in `scidk_prompt_17_01.txt`; human-purpose implementation tested.
A bounded explicit synthetic legacy snapshot is implemented;
operational legacy integration remains blocked on reliable source bindings and
catalog reconciliation.** Prompt 17 preflight,
2026-10-29, branch `design/knowledge-curation-20261029`, inspected HEAD
`19d4764075bf98ae0f02dfbfc044a90583f0ecc0`.

## Observed boundary and decision required

`scidk/services/knowledge_workspace.py` authorizes Research through AI tool
capabilities and resolves `FactDisclosure.store` policy. Similarly,
`scidk/services/review_workspace.py` authorizes the Review tool profile and resolves
`PolicyStore`. In `scidk/agent_tools/security.py`, a chat policy requires saved
provider settings matching an exact approved endpoint/model. Thus human browsing
and Review inspection depend on an AI destination, even when no model is called.
Research also reads current accepted/applied ledger facts only: legacy graph
presence is deliberately insufficient support, so removing the destination gate
alone would neither authorize nor reveal legacy records safely.

The existing Stage 3 administrative contract authorizes Resource classifications,
per-user Resource/evidence grants and AI destination ceilings. It does not define
a human purpose grant or a provider-independent human risk ceiling. Introducing
these is an authorization-policy decision. Prompt 17 P0-A requires stopping for
approval of a material policy change; this document requests that decision before
runtime changes or policy migrations. The operator subsequently approved this
contract explicitly in `scidk_prompt_17_01.txt` (renamed from the mistakenly named
`scidk_prompt_16_02.txt`). The proposal below is retained as the approved contract.

## Proposed narrow contract

1. **Principal and channel.** Governed human reads require an enabled named user
   with a current unlocked cookie session and existing same-origin checks.
   Anonymous/no-auth, API tokens, session headers and cross-origin requests deny.
   A distinct server-created human authorization context cannot be passed to AI
   tool dispatch or outbound context assembly.
2. **Explicit purpose authority.** A named existing administrator may issue or
   revoke an audited, versioned local per-user grant for `research_browse` and/or
   `review_read`, each with an explicit `low` or `medium` risk ceiling. Missing
   grants deny. No grants are inferred from role, login, provider settings or
   existing destination approval. Management initially uses trusted local
   administration, with no new HTTP policy editing endpoint.
3. **Resource and evidence authority.** Reuse the existing exact per-user Resource
   and evidence grants, classifications and property restrictions as additional
   mandatory checks. Every disclosed record must have an authorized source;
   relationships require both endpoints and all supporting evidence. Restricted
   evidence requires its explicit grant. Unknown or high classification denies
   this initial human adapter, including for administrators. This conservative
   ceiling does not establish an institution-wide policy for all human access.
4. **Review actions.** `review_read` permits only authorized inspection of proposed
   and historical assertions. Preview and decisions additionally require the
   existing reviewer authorization and actual ReviewService ledger path. An admin
   or reviewer role does not bypass Resource, evidence or purpose checks. Preserve
   explicit confirmation, expected revision and preview digest validation, and
   authorization of all disclosed dependencies/conflicts.
5. **Fresh checks.** Resolve current identity, purpose, classification, Resource,
   evidence and property permissions for each operation. Recheck at decision
   boundaries. Revocation or unavailable/malformed policy denies; no cached grant
   fallback. Keep requests, candidate scans and response sizes bounded.
6. **Legacy records.** Only a fixed, bounded, source-bound adapter with explicit
   stable external record identities may expose legacy data. A missing reliable
   source binding or identity withholds the record. Never add arbitrary Cypher or
   whole-graph fallback. Apply authorization before search, filtering, pagination
   or returned aggregates. Do not expose internal graph IDs, source locators,
   hidden properties or withheld counts. If existing storage cannot meet this
   contract, mark legacy browsing BLOCKED rather than weaken it.
7. **Honest status.** Legacy records are `legacy/unreviewed`; assertions retain
   their actual proposed/accepted/rejected/superseded state. Accepted decisions
   and applied materialization are separate states verified through existing
   ledger/receipt machinery. Inference/epistemic status remains independent of
   curation status. Browsing never creates decisions or acceptance receipts.
8. **AI separation.** Human grants do not approve any destination or disclosure to
   a model. Ask SciDK and Review assistant/proposal calls retain exact approved
   endpoint/model, existing content policy, consent, credential checks and
   authorization before and after transport. No fake provider configuration is
   used to unlock human browsing. Existing global credential/configuration gates
   and shared-use protections remain in force.

Approval would authorize implementing this contract and its local policy records;
it would not authorize production grants, production data access, ontology schema
changes, paid calls, service restarts or high-risk disclosure. Synthetic demo
grants would be explicit and confined to disposable state.

## Required verification after approval

These are acceptance requirements, **not test results**:

- Named explicitly granted users browse and inspect permitted Research/Review
  content with no provider; AI requests still fail closed without approval.
- Anonymous, no-auth, disabled/locked, token/header and cross-origin callers deny.
- An ordinary user without purpose/Resource grants, admin without Resource grants,
  and reviewer without evidence grants receive no protected content.
- Purpose/Resource/evidence revocation and classification changes take effect on
  the next operation; stale Review previews cannot commit decisions.
- Legacy hidden values cannot affect returned search results or counts; no raw
  locators/internal IDs appear. Unsupported source binding denies.
- Legacy/proposed/accepted/applied and epistemic status remain distinguishable.
- A human context cannot enter AI dispatch; disallowed endpoints/models still
  refuse, and transport-time revocation remains enforced.

The original preflight changed no runtime code or grants. Following approval,
`scidk/services/human_policy.py` implements explicit trusted-local initialization,
audited/versioned purpose grant and revocation, separate human identity and fresh
resolution. Human Research and Review HTTP adapters use named cookie sessions and
the existing fact/assertion serializers; AI adapters retain their original policy.
Research System/Ontology context tools retain their existing destination-bound
contract in this slice. `human_legacy.LegacySnapshot` reads only explicit bounded
source-bound snapshots, checks the actual ledger evidence scope and independent
record/evidence grants, and withholds locators and hidden properties. Its synthetic
demo records never enter AI discovery. No operational legacy adapter has been enabled without
reliable source-bound identities. See the Prompt 17 report for actual validation
results and incomplete integration work. No live service or provider settings
were changed and no paid requests were made.
