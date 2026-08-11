"""Attribution — rank target candidates for an anchor node, write back an edge.

Given an *anchor* node in the graph (an ``Investigator``, a ``Lab``, a ``Study``
-- any label), find *target* nodes across every scanned source whose path carries
some spelling of the anchor's name, score each by how likely the attribution is,
and let a staff member confirm the good ones as ``(:Anchor)-[:REL]->(:Target)``
edges.

Nothing here is specific to people or to folders: the anchor label, the target
label and the relationship type are all caller-supplied. ``Investigator``,
``Folder`` and ``OWNS`` are only the defaults.

Scoring is a heuristic over the path string, not evidence:

* how deep the target sits below its scan root — a name at depth 1 is a home
  directory, the same name at depth 8 is probably a mention
* whether the path also names an imaging modality
* whether the name that matched was the anchor's or a labmate's

Every query here is a single round trip. Name variants and target paths go over
as bound parameters; the identifiers that *must* be interpolated -- the two
labels and the relationship type -- are whitelisted through ``filter_builder``
first: :func:`~scidk.services.filter_builder._validate_identifier` for labels,
:func:`~scidk.services.filter_builder._validate_rel_type` for the edge, which
additionally enforces the uppercase Cypher convention.

Consumers: the ``/api/files/attribution/*`` routes in ``web/routes/api_files.py``
and the attribution panel in ``ui/templates/datasets.html``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .filter_builder import _validate_identifier, _validate_rel_type

__all__ = [
    "DEFAULT_ANCHOR_LABEL",
    "DEFAULT_RELATIONSHIP",
    "DEFAULT_TARGET_LABEL",
    "MODALITY_KEYWORDS",
    "RELATIONSHIP_FALLBACKS",
    "RELATIONSHIP_SUGGESTIONS",
    "AttributionCandidate",
    "ConfirmResult",
    "FolderAttributionService",
]

#: Node label targets are attributed *from* when the caller names none.
#: Not baked into the queries -- every entry point takes an ``anchor_label``,
#: because which label carries people differs per deployment. ``Person`` is the
#: shared label :meth:`FolderAttributionService.ensure_person_label` applies
#: across ``Investigator`` and ``User``, and works as an anchor spanning both.
DEFAULT_ANCHOR_LABEL = 'Investigator'

#: Node label attributed *to* when the caller names none.
DEFAULT_TARGET_LABEL = 'Folder'

#: Edge written on confirm when the caller names none.
DEFAULT_RELATIONSHIP = 'OWNS'


@dataclass
class AttributionCandidate:
    path:               str
    name:               str
    host_id:            str
    scan_root:          str
    relative_depth:     int
    confidence:         str   # "HIGH" | "MED" | "LOW"
    reason:             str
    matched_variant:    str
    has_modality_match: bool
    is_labmate_folder:  bool


@dataclass
class ConfirmResult:
    written: int
    skipped: int
    errors:  list


#: Modality shorthand -> the substrings that betray it in a folder path.
MODALITY_KEYWORDS: Dict[str, List[str]] = {
    'ultrasound': ['ultrasound', 'vevo', 'us_', '_us_'],
    'microct':    ['microct', 'micro-ct', 'micro_ct', 'bruker', 'skyscan'],
    'ivis':       ['ivis', 'livingimage', 'living_image', 'xenogen'],
    'histology':  ['histology', 'histo', 'pathology'],
    'flow':       ['flow', 'facs', 'cytometry'],
}

#: Seed relationship types per (anchor label, target label) pair. These are
#: *suggestions only* -- :meth:`FolderAttributionService.get_relationship_suggestions`
#: merges them with whatever the live graph already uses between the same two
#: labels, so a deployment's own vocabulary surfaces without editing this dict.
#: Order matters: the first entry of a pair is what the UI preselects.
RELATIONSHIP_SUGGESTIONS: Dict[Tuple[str, str], List[str]] = {
    ("Investigator", "Folder"):  ["OWNS", "CONTRIBUTED_TO", "GENERATED"],
    ("Investigator", "File"):    ["OWNS", "CONTRIBUTED_TO", "GENERATED"],
    ("Investigator", "Dataset"): ["OWNS", "CONTRIBUTED_TO", "GENERATED"],
    ("User",         "Folder"):  ["OWNS", "CONTRIBUTED_TO"],
    ("User",         "File"):    ["OWNS", "CONTRIBUTED_TO"],
    ("User",         "Dataset"): ["OWNS", "CONTRIBUTED_TO"],
    ("Lab",          "Folder"):  ["OWNS", "MANAGES", "CONTAINS"],
    ("Lab",          "File"):    ["OWNS", "MANAGES"],
    ("Lab",          "Dataset"): ["OWNS", "MANAGES", "CONTAINS"],
    ("Study",        "Folder"):  ["CONTAINS", "GENERATED"],
    ("Study",        "File"):    ["CONTAINS", "GENERATED"],
    ("Study",        "Dataset"): ["CONTAINS", "GENERATED"],
    ("CACProtocol",  "Folder"):  ["CONTAINS", "GENERATED"],
    ("CACProtocol",  "File"):    ["CONTAINS", "GENERATED"],
    ("CACProtocol",  "Dataset"): ["CONTAINS", "GENERATED"],
    ("Request",      "Folder"):  ["CONTAINS", "GENERATED"],
    ("Request",      "Dataset"): ["CONTAINS", "GENERATED"],
}

#: Appended to every suggestion list, so a pair with no seeds and an empty graph
#: still offers something usable.
RELATIONSHIP_FALLBACKS: List[str] = ["OWNS", "CONTAINS", "RELATED_TO"]

#: Shortest name variant worth matching. Three characters or fewer produce
#: substring hits in unrelated paths far more often than real attributions.
MIN_VARIANT_LEN = 4


class FolderAttributionService:
    """Attribution against a live Neo4j graph.

    The caller owns the driver's lifetime; this class never closes it.
    Construction is free of side effects -- it runs no queries, so the routes can
    build one per request against a shared driver.
    """

    #: ``:Person`` backfill is process-wide state, not per-instance -- the
    #: routes build a service per request and the write must not repeat.
    _person_label_applied = False

    def __init__(self, neo4j_driver, database: Optional[str] = None):
        self.driver = neo4j_driver
        self.database = database

    def _session(self):
        if self.database:
            return self.driver.session(database=self.database)
        return self.driver.session()

    # ------------------------------------------------------------------
    # Schema

    def ensure_person_label(self, force: bool = False) -> None:
        """Give every ``Investigator`` and ``User`` node the shared ``:Person`` label.

        Idempotent -- the ``WHERE NOT n:Person`` guard means a second run writes
        nothing. Runs once per process unless ``force`` is set.

        Called from ``create_app()`` at startup, deliberately not from
        ``__init__``: the flag below is per-process, so a constructor call put
        these two writes on the first attribution request of every worker.
        """
        if FolderAttributionService._person_label_applied and not force:
            return
        with self._session() as session:
            session.run("MATCH (n:Investigator) WHERE NOT n:Person SET n:Person")
            session.run("MATCH (n:User) WHERE NOT n:Person SET n:Person")
        FolderAttributionService._person_label_applied = True

    # ------------------------------------------------------------------
    # Public

    def list_anchors(
        self,
        anchor_label:    str = DEFAULT_ANCHOR_LABEL,
        filter_property: Optional[str] = None,
        filter_value:    Optional[str] = None,
    ) -> List[dict]:
        """Every named node carrying ``anchor_label``, name-ordered, with its labels.

        Args:
            anchor_label: node label anchors are drawn from. Whitelisted before
                it reaches Cypher.
            filter_property: keep only nodes whose value for this property
                contains ``filter_value``. Whitelisted before it reaches Cypher
                -- a property key cannot travel as a bound parameter, so it has
                to be interpolated, so it has to be checked. Without it,
                ``filter_value`` is ignored: there is nothing to match against.
            filter_value: case-insensitive substring the property must contain,
                the same matching rule :meth:`_fetch_folders` uses. Empty or
                omitted matches every node that carries ``filter_property`` at
                all -- the useful reading of "filter by email" before an email
                has been typed.

        Returns:
            ``{"name", "labels"}`` per anchor, plus ``"matched_value"`` -- the
            property value that matched -- when a property filter is in play.

        Raises:
            ValueError: ``anchor_label`` or ``filter_property`` is not a legal
                Cypher identifier.
        """
        label = _validate_identifier(anchor_label)

        if filter_property:
            prop = _validate_identifier(filter_property)
            # ``p.name IS NOT NULL`` holds on this branch too, not just the
            # unfiltered one: an anchor is picked, searched and written back by
            # name (see :meth:`confirm`), so a nameless match cannot be used for
            # anything and would only show up as a blank row in the picker.
            with self._session() as session:
                result = session.run(
                    f"MATCH (p:{label}) "
                    "WHERE p.name IS NOT NULL "
                    f"  AND p.{prop} IS NOT NULL "
                    f"  AND toLower(toString(p.{prop})) CONTAINS toLower($val) "
                    "RETURN p.name AS name, labels(p) AS labels, "
                    f"       p.{prop} AS matched_value "
                    "ORDER BY p.name",
                    val=(filter_value or '')
                )
                return [dict(r) for r in result]

        with self._session() as session:
            result = session.run(
                f"MATCH (p:{label}) WHERE p.name IS NOT NULL "
                "RETURN p.name AS name, labels(p) AS labels "
                "ORDER BY p.name"
            )
            return [dict(r) for r in result]

    def list_anchor_properties(self, anchor_label: str) -> List[str]:
        """Property keys present on at least one ``anchor_label`` node, commonest first.

        Populates the property picker in the attribution panel, so the user can
        narrow anchors by whatever those nodes actually carry -- ``email``,
        ``lab``, ``orcid`` -- instead of only by ``name``. Derived from the data
        rather than declared anywhere: a deployment that adds a property to its
        people gets it in the picker with no code change.

        Counting and ordering happen in the database, in one round trip; a label
        with no nodes is an empty list, not an error.

        Raises:
            ValueError: ``anchor_label`` is not a legal Cypher identifier.
        """
        label = _validate_identifier(anchor_label)
        with self._session() as session:
            result = session.run(f"""
                MATCH (n:{label})
                UNWIND keys(n) AS key
                RETURN key, count(*) AS cnt
                ORDER BY cnt DESC
            """)
            return [row['key'] for row in result if row['key']]

    def list_anchor_property_values(
        self,
        anchor_label: str,
        property_key: str,
    ) -> List[str]:
        """Distinct non-null values of ``property_key`` on ``anchor_label`` nodes, sorted.

        Fills the value picker that sits beside the property picker, so narrowing
        anchors by ``lab`` or ``email`` is a choice among what the graph holds
        rather than a substring the user has to already know. Like
        :meth:`list_anchor_properties`, the list is derived from the data, so a
        deployment gets its own vocabulary with no code change.

        Values come back as strings -- ``toString`` in the query rather than
        ``str()`` here, so the distinctness and the ordering are the database's
        and stay consistent for numeric or temporal properties. Distinctness is
        over the *rendered* value: two nodes whose property differs only by type
        collapse to one option, which is what a picker wants.

        ``property_key`` cannot travel as a bound parameter, so it is
        interpolated, so it is whitelisted first -- the same rule as the
        ``filter_property`` branch of :meth:`list_anchors`.

        Raises:
            ValueError: either argument is not a legal Cypher identifier.
        """
        label = _validate_identifier(anchor_label)
        prop = _validate_identifier(property_key)
        with self._session() as session:
            result = session.run(f"""
                MATCH (n:{label})
                WHERE n.{prop} IS NOT NULL
                RETURN DISTINCT toString(n.{prop}) AS val
                ORDER BY val
            """)
            return [row['val'] for row in result if row['val']]

    def get_relationship_suggestions(
        self,
        anchor_label: str = DEFAULT_ANCHOR_LABEL,
        target_label: str = DEFAULT_TARGET_LABEL,
    ) -> List[str]:
        """Ordered relationship types to offer for an anchor -> target pair.

        Three sources, concatenated in this order and then deduplicated:

        1. the pair's seeds in :data:`RELATIONSHIP_SUGGESTIONS`
        2. types that already connect these two labels in the live graph, most
           used first
        3. :data:`RELATIONSHIP_FALLBACKS`

        Seeds lead so a known-good type is preselected, but the graph-discovered
        set is what makes this useful over time: as real attributions accumulate,
        a deployment's own vocabulary rises into the list without anyone editing
        the dict. A discovered type that is not uppercase is dropped -- it cannot
        be written back through :meth:`confirm`, so offering it would be a
        dead end.

        Raises:
            ValueError: either label is not a legal Cypher identifier.
        """
        safe_anchor = _validate_identifier(anchor_label)
        safe_target = _validate_identifier(target_label)

        defaults = RELATIONSHIP_SUGGESTIONS.get((safe_anchor, safe_target), [])

        # A missing label, or no edges between the two, is an empty list rather
        # than an error: the picker still has seeds and fallbacks to offer.
        try:
            with self._session() as session:
                result = session.run(
                    f"MATCH (a:{safe_anchor})-[r]->(t:{safe_target}) "
                    "RETURN type(r) AS rel_type, count(*) AS cnt "
                    "ORDER BY cnt DESC"
                )
                graph_rels = [row['rel_type'] for row in result if row['rel_type']]
        except Exception:
            graph_rels = []

        suggestions: List[str] = []
        seen = set()
        for rel in list(defaults) + graph_rels + RELATIONSHIP_FALLBACKS:
            if rel in seen:
                continue
            try:
                _validate_rel_type(rel)
            except ValueError:
                continue
            seen.add(rel)
            suggestions.append(rel)
        return suggestions

    def get_candidates(
        self,
        anchor_name:       str,
        modality_keywords: Optional[List[str]] = None,
        include_labmates:  bool = True,
        sources:           Optional[List[str]] = None,
        anchor_label:      str = DEFAULT_ANCHOR_LABEL,
        target_label:      str = DEFAULT_TARGET_LABEL,
    ) -> List[AttributionCandidate]:
        """Rank ``target_label`` nodes that may belong to ``anchor_name``.

        Args:
            anchor_name: exact ``name`` of the anchor node to attribute targets to.
            modality_keywords: modality shorthands (see :data:`MODALITY_KEYWORDS`)
                or raw substrings. A hit promotes the confidence of a match.
            include_labmates: also match targets named for someone sharing a
                ``:Lab`` with this anchor -- those score MED at best.
            sources: restrict to these ``Scan.host_id`` values; all sources
                when omitted.
            anchor_label: node label anchors are matched under. Whitelisted
                before it reaches Cypher.
            target_label: node label candidates are drawn from. Whitelisted
                before it reaches Cypher. Must carry ``path`` and be reachable
                from a ``:Scan`` by ``SCANNED_IN``.

        Returns:
            Candidates sorted HIGH -> MED -> LOW, shallowest first within a tier.

        Raises:
            ValueError: either label is not a legal Cypher identifier.
        """
        label = _validate_identifier(anchor_label)
        target = _validate_identifier(target_label)
        variants = self._name_variants(anchor_name)

        labmate_variants: List[str] = []
        if include_labmates:
            for labmate in self._get_labmates(anchor_name, label):
                labmate_variants.extend(self._name_variants(labmate))

        # Own variants win ties, so they must not also appear in the labmate
        # list -- a shared surname would otherwise downgrade a real match.
        own_lower = {v.lower() for v in variants}
        labmate_variants = [v for v in labmate_variants if v.lower() not in own_lower]

        if not variants and not labmate_variants:
            return []

        keywords = self._resolve_keywords(modality_keywords)
        folders = self._fetch_folders(sources, variants + labmate_variants, target)

        candidates: List[AttributionCandidate] = []
        seen = set()

        for f in folders:
            path = f['path'] or ''
            path_lower = path.lower()
            if path in seen:
                continue

            matched_variant = None
            is_labmate_folder = False

            for v in variants:
                if v.lower() in path_lower:
                    matched_variant = v
                    break

            if matched_variant is None:
                for v in labmate_variants:
                    if v.lower() in path_lower:
                        matched_variant = v
                        is_labmate_folder = True
                        break

            if matched_variant is None:
                continue

            has_modality = any(kw in path_lower for kw in keywords)
            depth = self._relative_depth(path, f['scan_root'] or '')
            conf, reason = self._score(depth, matched_variant,
                                       is_labmate_folder, has_modality)
            seen.add(path)
            candidates.append(AttributionCandidate(
                path               = path,
                name               = f['name'] or '',
                host_id            = f['host_id'] or '',
                scan_root          = f['scan_root'] or '',
                relative_depth     = depth,
                confidence         = conf,
                reason             = reason,
                matched_variant    = matched_variant,
                has_modality_match = has_modality,
                is_labmate_folder  = is_labmate_folder,
            ))

        order = {'HIGH': 0, 'MED': 1, 'LOW': 2}
        candidates.sort(key=lambda c: (order[c.confidence], c.relative_depth, c.path))
        return candidates

    def confirm(
        self,
        anchor_name:  str,
        target_paths: Optional[List[str]] = None,
        confirmed_by: str = 'system',
        anchor_label: str = DEFAULT_ANCHOR_LABEL,
        target_label: str = DEFAULT_TARGET_LABEL,
        relationship: str = DEFAULT_RELATIONSHIP,
    ) -> ConfirmResult:
        """Write ``relationship`` edges from ``anchor_name`` to each target path.

        One round trip for the whole batch. Paths that match no ``target_label``
        node -- or every path, if the anchor does not exist -- come back as errors
        rather than silently counting as skipped.

        Raises:
            ValueError: either label is not a legal Cypher identifier, or
                ``relationship`` is not an uppercase Cypher relationship type.
        """
        label = _validate_identifier(anchor_label)
        target = _validate_identifier(target_label)
        rel = _validate_rel_type(relationship)
        paths = [p for p in (target_paths or []) if p]
        if not paths:
            return ConfirmResult(written=0, skipped=0, errors=[])

        try:
            with self._session() as session:
                result = session.run(f"""
                    MATCH (p:{label} {{name: $name}})
                    UNWIND $paths AS target
                    MATCH (f:{target} {{path: target}})
                    MERGE (p)-[rel:{rel}]->(f)
                    ON CREATE SET
                        rel.confirmed_by = $by,
                        rel.confirmed_at = $ts,
                        rel.method       = 'attribution_panel'
                    RETURN DISTINCT target AS path
                """, name=anchor_name, paths=paths,
                     by=confirmed_by,
                     ts=datetime.now(timezone.utc).isoformat())
                matched = {r['path'] for r in result}
                written = result.consume().counters.relationships_created
        except Exception as e:
            return ConfirmResult(written=0, skipped=0,
                                 errors=[f"attribution write failed: {e}"])

        errors = [f"{p}: no :{label} {anchor_name!r} or no :{target} with that path"
                  for p in paths if p not in matched]
        return ConfirmResult(
            written = written,
            skipped = max(0, len(matched) - written),
            errors  = errors,
        )

    # ------------------------------------------------------------------
    # Private helpers

    def _name_variants(self, full_name: str) -> List[str]:
        """Plausible spellings of a name as they appear in folder paths.

        Ordered most- to least-specific: the first hit wins, so ``Jingwei Zhang``
        beats ``jzhang`` when a path contains both.
        """
        parts = (full_name or '').strip().split()
        if len(parts) < 2:
            name = (full_name or '').strip()
            return [name] if len(name) >= MIN_VARIANT_LEN else []
        first, *_, last = parts
        variants = [
            full_name.strip(),
            f"{last} {first}",
            f"{last}, {first}",
            f"{first}{last}",
            f"{first}_{last}",
            f"{first}.{last}",
            f"{first[0]}{last}",
            f"{first[0]}_{last}",
            f"{first[0].lower()}{last.lower()}",
            f"{first.lower()}.{last.lower()}",
        ]
        # Dedupe case-insensitively, preserving specificity order.
        out, seen = [], set()
        for v in variants:
            if len(v) < MIN_VARIANT_LEN or v.lower() in seen:
                continue
            seen.add(v.lower())
            out.append(v)
        return out

    def _relative_depth(self, path: str, scan_root: str) -> int:
        """How many path segments separate a folder from its scan root."""
        relative = path[len(scan_root):] if scan_root and path.startswith(scan_root) else path
        relative = relative.strip('/')
        return len(relative.split('/')) if relative else 0

    def _score(self, depth, variant, is_labmate, has_modality):
        """Confidence tier plus the human-readable reason behind it."""
        if is_labmate:
            if has_modality:
                return 'MED', f"labmate folder · '{variant}' + modality keyword"
            return 'LOW', f"labmate folder · '{variant}'"
        if depth <= 2:
            r = f"name match '{variant}' at depth {depth}"
            return 'HIGH', r + (' + modality' if has_modality else '')
        if depth <= 5:
            r = f"name match '{variant}' at depth {depth}"
            return 'MED', r + (' + modality' if has_modality else '')
        return 'LOW', f"name match '{variant}' at depth {depth} (deep)"

    def _resolve_keywords(self, modality_keywords) -> List[str]:
        """Expand modality shorthands to path substrings; pass others through."""
        if not modality_keywords:
            return []
        out: List[str] = []
        for kw in modality_keywords:
            if not kw:
                continue
            out.extend(MODALITY_KEYWORDS.get(str(kw).lower(), [str(kw).lower()]))
        return out

    def _get_labmates(self, anchor_name: str, label: str) -> List[str]:
        """Names of everyone sharing a ``:Lab`` with this anchor.

        ``label`` must already be whitelisted -- callers validate it once and
        pass it down rather than re-checking per query.
        """
        with self._session() as session:
            r = session.run(f"""
                MATCH (p:{label} {{name: $name}})-[:MEMBER_OF]->(lab:Lab)
                      <-[:MEMBER_OF]-(lm:{label})
                WHERE lm.name <> $name
                RETURN DISTINCT lm.name AS name
            """, name=anchor_name)
            return [row['name'] for row in r if row['name']]

    def _fetch_folders(
        self,
        sources,
        variants,
        target_label: str = DEFAULT_TARGET_LABEL,
    ) -> List[dict]:
        """Targets whose path contains any name variant, optionally scoped by source.

        The name filter runs in the database rather than in Python: pulling every
        ``:Folder`` back over the wire is not viable at this graph's size. Variants
        arrive lowercased as a bound list -- never interpolated. ``target_label``
        must already be whitelisted by the caller.
        """
        needles = sorted({v.lower() for v in variants if len(v) >= MIN_VARIANT_LEN})
        if not needles:
            return []
        with self._session() as session:
            result = session.run(f"""
                MATCH (f:{target_label})-[:SCANNED_IN]->(s:Scan)
                WHERE ($sources IS NULL OR s.host_id IN $sources)
                  AND any(v IN $needles WHERE toLower(f.path) CONTAINS v)
                RETURN f.path AS path, f.name AS name,
                       s.host_id AS host_id, s.path AS scan_root
            """, sources=(sources or None), needles=needles)
            return [dict(r) for r in result]
