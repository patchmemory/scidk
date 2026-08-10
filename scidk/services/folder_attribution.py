"""Folder attribution — rank folder candidates for a person, write back OWNS_FOLDER.

Given a person in the graph, find folders across every scanned source whose path
carries some spelling of that person's name, score each by how likely it is to
actually be theirs, and let a staff member confirm the good ones as
``(:Person)-[:OWNS_FOLDER]->(:Folder)`` edges.

Scoring is a heuristic over the path string, not evidence:

* how deep the folder sits below its scan root — a name at depth 1 is a home
  directory, the same name at depth 8 is probably a mention
* whether the path also names an imaging modality
* whether the name that matched was the person's or a labmate's

Every query here is a single round trip. Name variants and folder paths go over
as bound parameters -- nothing user-supplied is interpolated into Cypher.

Consumers: the ``/api/files/attribution/*`` routes in ``web/routes/api_files.py``
and the attribution panel in ``ui/templates/datasets.html``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .filter_builder import _validate_identifier

__all__ = [
    "DEFAULT_ANCHOR_LABEL",
    "MODALITY_KEYWORDS",
    "AttributionCandidate",
    "ConfirmResult",
    "FolderAttributionService",
]

#: Node label folders are attributed *from* when the caller names none.
#: Not baked into the queries -- every entry point takes an ``anchor_label``,
#: because which label carries people differs per deployment. ``Person`` is the
#: shared label :meth:`FolderAttributionService.ensure_person_label` applies
#: across ``Investigator`` and ``User``, and works as an anchor spanning both.
DEFAULT_ANCHOR_LABEL = 'Investigator'


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

#: Shortest name variant worth matching. Three characters or fewer produce
#: substring hits in unrelated paths far more often than real attributions.
MIN_VARIANT_LEN = 4


class FolderAttributionService:
    """Folder attribution against a live Neo4j graph.

    The caller owns the driver's lifetime; this class never closes it.
    """

    #: ``:Person`` backfill is process-wide state, not per-instance -- the
    #: routes build a service per request and the write must not repeat.
    _person_label_applied = False

    def __init__(self, neo4j_driver, database: Optional[str] = None):
        self.driver = neo4j_driver
        self.database = database
        self.ensure_person_label()

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
        """
        if FolderAttributionService._person_label_applied and not force:
            return
        with self._session() as session:
            session.run("MATCH (n:Investigator) WHERE NOT n:Person SET n:Person")
            session.run("MATCH (n:User) WHERE NOT n:Person SET n:Person")
        FolderAttributionService._person_label_applied = True

    # ------------------------------------------------------------------
    # Public

    def list_persons(self, anchor_label: str = DEFAULT_ANCHOR_LABEL) -> List[dict]:
        """Every named node carrying ``anchor_label``, name-ordered, with its labels.

        Raises:
            ValueError: ``anchor_label`` is not a legal Cypher identifier.
        """
        label = _validate_identifier(anchor_label)
        with self._session() as session:
            result = session.run(
                f"MATCH (p:{label}) WHERE p.name IS NOT NULL "
                "RETURN p.name AS name, labels(p) AS labels "
                "ORDER BY p.name"
            )
            return [dict(r) for r in result]

    def get_candidates(
        self,
        person_name:       str,
        modality_keywords: Optional[List[str]] = None,
        include_labmates:  bool = True,
        sources:           Optional[List[str]] = None,
        anchor_label:      str = DEFAULT_ANCHOR_LABEL,
    ) -> List[AttributionCandidate]:
        """Rank folders that may belong to ``person_name``.

        Args:
            person_name: exact ``name`` of the anchor node to attribute folders to.
            modality_keywords: modality shorthands (see :data:`MODALITY_KEYWORDS`)
                or raw substrings. A hit promotes the confidence of a match.
            include_labmates: also match folders named for someone sharing a
                ``:Lab`` with this person -- those score MED at best.
            sources: restrict to these ``Scan.host_id`` values; all sources
                when omitted.
            anchor_label: node label people are matched under. Whitelisted
                before it reaches Cypher.

        Returns:
            Candidates sorted HIGH -> MED -> LOW, shallowest first within a tier.

        Raises:
            ValueError: ``anchor_label`` is not a legal Cypher identifier.
        """
        label = _validate_identifier(anchor_label)
        variants = self._name_variants(person_name)

        labmate_variants: List[str] = []
        if include_labmates:
            for labmate in self._get_labmates(person_name, label):
                labmate_variants.extend(self._name_variants(labmate))

        # Own variants win ties, so they must not also appear in the labmate
        # list -- a shared surname would otherwise downgrade a real match.
        own_lower = {v.lower() for v in variants}
        labmate_variants = [v for v in labmate_variants if v.lower() not in own_lower]

        if not variants and not labmate_variants:
            return []

        keywords = self._resolve_keywords(modality_keywords)
        folders = self._fetch_folders(sources, variants + labmate_variants)

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
        person_name:  str,
        folder_paths: List[str],
        confirmed_by: str = 'system',
        anchor_label: str = DEFAULT_ANCHOR_LABEL,
    ) -> ConfirmResult:
        """Write ``OWNS_FOLDER`` edges from ``person_name`` to each folder path.

        One round trip for the whole batch. Paths that match no ``Folder`` -- or
        every path, if the person does not exist -- come back as errors rather
        than silently counting as skipped.

        Raises:
            ValueError: ``anchor_label`` is not a legal Cypher identifier.
        """
        label = _validate_identifier(anchor_label)
        paths = [p for p in (folder_paths or []) if p]
        if not paths:
            return ConfirmResult(written=0, skipped=0, errors=[])

        try:
            with self._session() as session:
                result = session.run(f"""
                    MATCH (p:{label} {{name: $name}})
                    UNWIND $paths AS target
                    MATCH (f:Folder {{path: target}})
                    MERGE (p)-[rel:OWNS_FOLDER]->(f)
                    ON CREATE SET
                        rel.confirmed_by = $by,
                        rel.confirmed_at = $ts,
                        rel.method       = 'attribution_panel'
                    RETURN DISTINCT target AS path
                """, name=person_name, paths=paths,
                     by=confirmed_by,
                     ts=datetime.now(timezone.utc).isoformat())
                matched = {r['path'] for r in result}
                written = result.consume().counters.relationships_created
        except Exception as e:
            return ConfirmResult(written=0, skipped=0,
                                 errors=[f"attribution write failed: {e}"])

        errors = [f"{p}: no :{label} {person_name!r} or no :Folder with that path"
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

    def _get_labmates(self, person_name: str, label: str) -> List[str]:
        """Names of everyone sharing a ``:Lab`` with this person.

        ``label`` must already be whitelisted -- callers validate it once and
        pass it down rather than re-checking per query.
        """
        with self._session() as session:
            r = session.run(f"""
                MATCH (p:{label} {{name: $name}})-[:MEMBER_OF]->(lab:Lab)
                      <-[:MEMBER_OF]-(lm:{label})
                WHERE lm.name <> $name
                RETURN DISTINCT lm.name AS name
            """, name=person_name)
            return [row['name'] for row in r if row['name']]

    def _fetch_folders(self, sources, variants) -> List[dict]:
        """Folders whose path contains any name variant, optionally scoped by source.

        The name filter runs in the database rather than in Python: pulling every
        ``:Folder`` back over the wire is not viable at this graph's size. Variants
        arrive lowercased as a bound list -- never interpolated.
        """
        needles = sorted({v.lower() for v in variants if len(v) >= MIN_VARIANT_LEN})
        if not needles:
            return []
        with self._session() as session:
            result = session.run("""
                MATCH (f:Folder)-[:SCANNED_IN]->(s:Scan)
                WHERE ($sources IS NULL OR s.host_id IN $sources)
                  AND any(v IN $needles WHERE toLower(f.path) CONTAINS v)
                RETURN f.path AS path, f.name AS name,
                       s.host_id AS host_id, s.path AS scan_root
            """, sources=(sources or None), needles=needles)
            return [dict(r) for r in result]
