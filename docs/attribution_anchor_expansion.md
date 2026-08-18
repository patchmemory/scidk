# Attribution — Anchor Expansion (Future Spec)

## The problem

The current attribution panel takes a single anchor node and searches for
target nodes whose paths carry some spelling of its name. This works for
one person, but many real queries are neighborhood-shaped:

- "Find folders belonging to anyone in Zhang's lab"
- "Find datasets associated with this protocol and its co-investigators"
- "Find files scanned by any instrument this PI has access to"

These are graph traversal problems: start from an anchor, walk N hops
along specified relationship types, collect the names of reached nodes,
and use the union of their name variants as the needle set.

## Proposed approach

Add an optional `anchor_expansion` parameter to `get_candidates`:

```python
anchor_expansion: Optional[List[{
    'relationship': str,   # e.g. 'MEMBER_OF'
    'direction': str,      # 'out' | 'in' | 'both'
    'hops': int,           # default 1
    'target_label': str,   # label of nodes to collect names from
}]] = None
```

The service walks each expansion pattern from the anchor node, collects
`name` properties from reached nodes, and adds their variants to the
needle set alongside the anchor's own variants. Scoring distinguishes
direct matches (anchor's own variants) from expanded matches (related
node variants), as `is_labmate_folder` does today but generalized.

## UI

A collapsible "Also search nearby nodes" section below the Anchor picker,
with rows of [relationship type ⌄] [direction ⌄] [hops ⌄] [label ⌄].
Pre-populate with the curated patterns from the evaluation doc
(Lab members via MEMBER_OF, Project co-investigators via PI_OF).
Allow adding custom rows for power users.

## Dependencies

- Curated pattern registry from evaluation doc section 3
- Verification that MEMBER_OF / Lab nodes exist in the target deployment
- Decision on whether `:Person` backfill (ensure_person_label) covers
  all relevant anchor labels before traversal
