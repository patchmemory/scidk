"""The FAIR check — what a run would write, reported before it writes it.

Cycle 3B Task E. :meth:`~scidk.pipeline.runner.PipelineRunner.preflight` answers
"could this source run at all" from config alone. This module answers the harder
question the user actually asks before committing to the graph: *what would come
out, and which of it is new?* It samples rows, resolves each one through the same
mapping engine a real run uses, and looks every resolved merge key up in the live
graph, so a preview line can say ``[new]`` or ``[merge]`` rather than guessing.

Zero writes, by construction rather than by care
------------------------------------------------
Nothing here can write. The row sample comes from
:meth:`~scidk.pipeline.runner.PipelineRunner.resolve_rows`, which never touches a
writer, and the graph is reached through a
:class:`~scidk.pipeline.runner.Neo4jReader` — a protocol with ``execute_read`` and
nothing else. A FAIR check on a source whose runner has a writer attached still
writes nothing, because it never asks for one.

The four letters, and how they differ from ``preflight()``
---------------------------------------------------------
======= =============================================================
``F``   ``find()`` succeeded; its column list is what ``I`` validates
        the mapping against.
``A``   ``access()`` succeeded. Independent of the mapping — whether a
        credential works is not a question about columns.
``I``   The config validates, every column it needs exists, and a
        sample of real rows resolves through it.
``R``   Nothing has drifted since this source's last successful run:
        row count, column set, key resolution rate. Warnings only —
        ``R`` never fails, and a first run always passes it.
======= =============================================================

``R`` therefore means something narrower here than in ``preflight()``, where it is
"every transform the config names resolves". Nothing is lost: an unknown transform
is a config error, so :meth:`~scidk.pipeline.mapping_engine.MappingEngine.validate`
already reports it and it fails ``I`` — before a single row is fetched.

The letters run in strict sequence and stop at the first hard failure. A letter
never reached is reported as ``'skipped'``, not as a pass and not as a failure:
"the credential was rejected so the mapping was never checked" is a different
thing to say than "the mapping is fine".

Coupling worth knowing about
----------------------------
:func:`_classify_row_errors` reads the *wording* of the messages
:class:`~scidk.pipeline.mapping_engine.RowMapping` carries, because the engine
reports a row's problems as human-readable strings and this report needs them
split by kind and attributed to a column. ``tests/pipeline/test_fair_check.py``
pins those phrases deliberately: if the engine rewords one, a test fails rather
than the user quietly losing the transform-failure column.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Set, Tuple

from .identifiers import check_identifier
from .mapping_engine import MappingConfigError, RowMapping
from .runner import Neo4jReader, PipelineRunner
from .store import utc_now

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SAMPLE_SIZE",
    "FAIL",
    "KEY_FAILURE_FAIL_RATIO",
    "MAX_SAMPLE_SIZE",
    "PASS",
    "PriorRun",
    "SKIPPED",
    "WARN",
    "clamp_sample_size",
    "neo4j_key_lookup",
    "prior_run_for_source",
    "run_fair_check",
]

#: Rows sampled when the caller does not say. Ten is enough to see a mapping
#: work and cheap enough to run on every button press.
DEFAULT_SAMPLE_SIZE = 10

#: Hard ceiling on ``sample_size``. Every sampled row costs a mapping pass and
#: contributes to a per-(label, key) graph read, and a preview nobody can read is
#: not a better preview.
MAX_SAMPLE_SIZE = 50

#: Above this share of sampled rows failing key resolution, ``I`` fails rather
#: than warns: at that point the mapping is not "mostly working".
KEY_FAILURE_FAIL_RATIO = 0.2

#: Row-count change against the last successful run that ``R`` warns about.
ROW_COUNT_DRIFT_WARN = 0.1

#: Cap on each list of per-row failures, so one systematically broken column in a
#: 50-row sample cannot produce an unreadable report. Counts stay exact.
MAX_REPORTED_FAILURES = 50

PASS = "pass"
WARN = "warn"
FAIL = "fail"
#: A letter the sequence never reached, because an earlier one failed.
SKIPPED = "skipped"

#: Engine row messages that mean "no merge key could be resolved". The two
#: phrasings are ``_finalize``'s: no candidate key property was non-empty, and a
#: key that resolved to a list or dict.
_KEY_FAILURE_MARKERS = ("no non-empty key property", "merge key")

#: ``row 3: pi.email: <what went wrong>`` — a transform or property failure the
#: engine attributed to one property of one node mapping.
_PROPERTY_ERROR_RE = re.compile(r"^row (\d+): ([^.:]+)\.([^:]+): (.+)$")

#: ``row 3: project.code is required but resolved empty; ...`` — same attribution,
#: different shape, because nothing follows the property name with a colon.
_REQUIRED_EMPTY_RE = re.compile(r"^row (\d+): ([^.:]+)\.(\S+) is required but resolved empty")

#: ``row 3: `` — stripped off a message before it is shown beside a 1-based row
#: number, so one line never carries two different numbers for the same row.
_ROW_PREFIX_RE = re.compile(r"^row \d+: ")

#: Property names that stand for "the mapping's shared source column" rather than
#: for a declared property, in the ``source``/``property_map`` form.
_SOURCE_PSEUDO_PROPERTIES = ("source", "source.fallback")


class KeyLookup(Protocol):
    """Which of these merge keys the graph already has.

    Args:
        label: Node label, already validated as a Cypher identifier.
        key_property: The property MERGE would key on.
        values: Candidate key values.

    Returns:
        The subset of ``values`` that exist, as strings — or None when the graph
        could not answer, which is reported as "unknown" rather than as "new".
    """

    def __call__(
        self, label: str, key_property: str, values: Sequence[Any]
    ) -> Optional[Set[str]]:
        ...


@dataclass
class PriorRun:
    """The last successful run of one source, as much of it as ``R`` compares.

    Attributes:
        ran_at: When it finished.
        pipeline_id: Which pipeline it was part of — the source's own implicit
            single-source pipeline, or a shared DAG it belongs to.
        summary: That step's :meth:`~scidk.pipeline.runner.RunReport.to_dict`.
    """

    ran_at: Optional[str] = None
    pipeline_id: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)


def clamp_sample_size(value: Any, default: int = DEFAULT_SAMPLE_SIZE) -> int:
    """Coerce a requested sample size into ``1..MAX_SAMPLE_SIZE``.

    Junk becomes the default rather than an error: ``?sample_size=lots`` is a
    request for a preview, not a reason to refuse one.
    """
    try:
        requested = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(requested, MAX_SAMPLE_SIZE))


def neo4j_key_lookup(reader: Neo4jReader) -> KeyLookup:
    """Build a :class:`KeyLookup` over a live graph. Reads only.

    One query per ``(label, key_property)`` group rather than one per node. The
    per-node form in the task block —
    ``MATCH (n:Label {key: $val}) RETURN count(n)`` — answers the same question a
    round trip at a time; grouping keeps a 50-row sample to a handful of reads.

    The label and key property are interpolated into Cypher, so they are checked
    here even though every :class:`~scidk.pipeline.mapping_engine.ResolvedNode`
    has already passed the engine's identifier gate. A caller skipping that gate
    must not be able to make this the injection point.
    """

    def lookup(
        label: str, key_property: str, values: Sequence[Any]
    ) -> Optional[Set[str]]:
        problem = (
            check_identifier(label, "label")
            or check_identifier(key_property, "key_property")
        )
        if problem:
            logger.warning("Refusing a FAIR key lookup: %s", problem)
            return None
        if not values:
            return set()

        query = (
            f"MATCH (n:{label}) WHERE n.{key_property} IN $values "
            f"RETURN DISTINCT n.{key_property} AS key"
        )
        try:
            rows = reader.execute_read(query, {"values": list(values)})
        except Exception as e:  # noqa: BLE001 - an unanswerable lookup is a result
            logger.warning("FAIR key lookup failed for :%s: %s", label, e)
            return None
        return {str(row.get("key")) for row in rows if row.get("key") is not None}

    return lookup


def prior_run_for_source(
    history: Any,
    source_id: str,
    pipeline_id: Optional[str] = None,
    scan_limit: int = 200,
) -> Optional[PriorRun]:
    """The most recent successful run of one source, or None.

    Args:
        history: Anything with ``list_runs(pipeline_id=None, limit=...)`` —
            :class:`~scidk.pipeline.run_history.RunHistory` in the app.
        source_id: The source whose step must have succeeded.
        pipeline_id: The source's implicit single-source pipeline, checked first.
        scan_limit: Runs examined per pass.

    The *step's* status is what is tested, not the run's: a DAG where one other
    source failed is still a run this source completed, and comparing against it
    is more useful than reporting no history. The implicit pipeline is preferred
    because that is where a source-level run lands, but a source that has only
    ever run inside a shared DAG still gets a baseline.
    """
    passes: List[List[Dict[str, Any]]] = []
    if pipeline_id:
        passes.append(history.list_runs(pipeline_id, limit=scan_limit) or [])
    passes.append(history.list_runs(limit=scan_limit) or [])

    for runs in passes:
        for run in runs:
            if run.get("in_flight") or not run.get("triggered_by"):
                continue
            for step in run.get("steps") or []:
                if str(step.get("source_id")) != str(source_id):
                    continue
                if step.get("status") != "success":
                    continue
                return PriorRun(
                    ran_at=run.get("completed_at") or run.get("started_at"),
                    pipeline_id=run.get("pipeline_id"),
                    summary=dict(step.get("summary") or {}),
                )
    return None


# --------------------------------------------------------------- the check

def run_fair_check(
    runner: PipelineRunner,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    key_lookup: Optional[KeyLookup] = None,
    lookup_unavailable: Optional[str] = None,
    prior: Optional[PriorRun] = None,
    mapping_problem: Optional[str] = None,
) -> Dict[str, Any]:
    """Run F, A, I and R in sequence and report what each found.

    Args:
        runner: A runner for the source. Its writer, if it has one, is never used.
        sample_size: Rows to process. Clamp with :func:`clamp_sample_size` first.
        key_lookup: The merge-vs-create lookup, or None to report every node's
            existence as unknown.
        lookup_unavailable: Why ``key_lookup`` is None, shown as an ``I`` warning
            so an unreachable graph reads as a gap in the report rather than as
            "everything is new".
        prior: What ``R`` compares against, from :func:`prior_run_for_source`.
        mapping_problem: A reason there is no usable mapping config at all, from
            the caller that built the runner. Reported as an ``I`` failure —
            ``F`` and ``A`` do not depend on a mapping and still run.

    Returns:
        The ``fair_status`` document: a dict per letter plus ``overall``,
        ``fair_ok``, ``sample_size`` and ``checked_at``. The top-level
        ``sample_size`` is what was *asked for* after clamping; ``I.sample_size``
        is how many rows the source actually had to give. Never raises: every
        failure mode here is something the user needs to read.
    """
    letters: Dict[str, Dict[str, Any]] = {
        letter: {"result": SKIPPED} for letter in ("F", "A", "I", "R")
    }
    requested = clamp_sample_size(sample_size)

    # F — Findable. Its column list is what I validates the mapping against, so
    # a failure here stops the sequence: there is nothing to cross-reference.
    find = runner.find()
    columns = [str(c) for c in (find.get("columns") or [])]
    row_count = find.get("row_count")
    if not find.get("ok"):
        letters["F"] = {
            "result": FAIL,
            "error": str(find.get("error") or "the source could not be found"),
            "columns": [],
            "row_count": None,
        }
        return _document(letters, requested)
    letters["F"] = {"result": PASS, "columns": columns, "row_count": row_count}

    # A — Accessible. Runs against the plugin, not against the mapping.
    access = runner.access()
    if not access.get("ok"):
        letters["A"] = {
            "result": FAIL,
            "error": str(access.get("error") or "access was denied"),
            "auth_method": access.get("auth_method"),
        }
        return _document(letters, requested)
    letters["A"] = {"result": PASS, "auth_method": access.get("auth_method")}

    # I — Interoperable. The config, then the columns, then real rows.
    letters["I"] = _interoperable(
        runner, columns, requested, key_lookup, lookup_unavailable, mapping_problem
    )
    if letters["I"]["result"] == FAIL:
        return _document(letters, requested)

    # R — Reproducible. Drift against the last successful run. Warnings only.
    letters["R"] = _reproducible(runner, prior, columns, row_count, letters["I"])
    return _document(letters, requested)


def _document(letters: Mapping[str, Dict[str, Any]], sample_size: int) -> Dict[str, Any]:
    """Assemble the stored ``fair_status`` document.

    ``fair_ok`` is kept alongside ``overall`` because it is what the earlier
    preflight wrote and what other callers already test; ``overall`` is the
    three-valued answer, since "runs but something drifted" is neither pass nor
    fail and merging it into either would hide it.
    """
    results = [letters[letter]["result"] for letter in ("F", "A", "I", "R")]
    if FAIL in results:
        overall = FAIL
    elif WARN in results:
        overall = WARN
    else:
        overall = PASS
    return {
        "check": "fair-check",
        "F": dict(letters["F"]),
        "A": dict(letters["A"]),
        "I": dict(letters["I"]),
        "R": dict(letters["R"]),
        "overall": overall,
        "fair_ok": overall == PASS,
        "sample_size": sample_size,
        "checked_at": utc_now(),
    }


def _interoperable(
    runner: PipelineRunner,
    columns: List[str],
    sample_size: int,
    key_lookup: Optional[KeyLookup],
    lookup_unavailable: Optional[str],
    mapping_problem: Optional[str],
) -> Dict[str, Any]:
    """The I step: validate, cross-reference, then sample real rows."""
    out: Dict[str, Any] = {
        "result": PASS,
        "missing_columns": [],
        "sample_size": 0,
        # 'resolved' and 'skipped' are about whether a row produced any node at
        # all. A row whose Project resolved and whose optional Person did not is
        # resolved *and* counted in rows_with_key_failure — one number cannot say
        # both, and collapsing them would hide the partial row either way.
        "rows_resolved": 0,
        "rows_skipped": 0,
        "rows_with_key_failure": 0,
        "nodes": {"total": 0, "new": 0, "merge": 0, "unknown": 0},
        "relationships": 0,
        "transform_failures": [],
        "key_failures": [],
        "other_failures": [],
        "preview": [],
        "errors": [],
        "warnings": [],
    }

    # 1. The config itself. A malformed mapping is reported as itself and nothing
    #    is fetched — validating after a read would blame the source for a typo.
    if mapping_problem:
        out["errors"].append(mapping_problem)
        out["result"] = FAIL
        return out
    try:
        validation = runner.engine.validate()
    except MappingConfigError as e:
        out["errors"].append(f"mapping: {e}")
        out["result"] = FAIL
        return out
    out["warnings"].extend(f"mapping: {m}" for m in validation.warnings)
    if not validation.ok:
        out["errors"].extend(f"mapping: {m}" for m in validation.errors)
        out["result"] = FAIL
        return out

    # 2. Cross-reference the mapping against the columns F actually found. A
    #    missing key column makes a node impossible and fails; a missing property
    #    column makes it incomplete and warns. MappingEngine.column_problems draws
    #    that line already, and drawing it twice would let the two disagree.
    out["missing_columns"] = runner.engine.missing_columns(columns)
    blocking, informational = runner.engine.column_problems(columns)
    out["errors"].extend(blocking)
    out["warnings"].extend(informational)
    if blocking:
        out["result"] = FAIL
        return out

    # 3. A sample of real rows, resolved by the same code path a run uses.
    try:
        rows = list(runner.resolve_rows(sample_size))
    except Exception as e:  # noqa: BLE001 - a broken stream is a result to show
        logger.warning("FAIR check could not read rows: %s", e, exc_info=True)
        out["errors"].append(f"fetch: {type(e).__name__}: {e}")
        out["result"] = FAIL
        return out

    out["sample_size"] = len(rows)
    if lookup_unavailable:
        out["warnings"].append(
            f"{lookup_unavailable}, so the preview cannot say which nodes already "
            "exist — every node is shown as unknown rather than as new"
        )

    existing = _existing_keys(rows, key_lookup)
    property_columns = runner.engine.property_columns()

    for row in rows:
        transform_failures, key_failures, other = _classify_row_errors(row, property_columns)
        _extend_capped(out["transform_failures"], transform_failures)
        _extend_capped(out["key_failures"], key_failures)
        _extend_capped(out["other_failures"], other)
        if key_failures:
            out["rows_with_key_failure"] += 1

        if row.nodes:
            out["rows_resolved"] += 1
        else:
            out["rows_skipped"] += 1
        out["relationships"] += len(row.relationships)
        for node in row.nodes:
            out["nodes"]["total"] += 1
            out["nodes"][_node_state(node, existing)] += 1

        out["preview"].append(_preview_line(row, existing))

    # 4. The verdict. A key that cannot resolve on more than a fifth of the sample
    #    is a broken mapping, not a few odd rows.
    failed = out["rows_with_key_failure"]
    failure_ratio = failed / len(rows) if rows else 0.0
    out["key_failure_ratio"] = round(failure_ratio, 3)
    if failed:
        out["warnings"].append(
            f"{failed} of {len(rows)} sample row(s) failed key resolution"
        )
    if failure_ratio > KEY_FAILURE_FAIL_RATIO:
        out["errors"].append(
            f"{failed} of {len(rows)} sample rows could not resolve a merge key — "
            f"more than the {KEY_FAILURE_FAIL_RATIO:.0%} this check treats as a "
            "broken mapping rather than as bad rows"
        )
    if not rows:
        out["warnings"].append(
            "the source has no rows, so nothing could be previewed"
        )

    if out["errors"]:
        out["result"] = FAIL
    elif out["warnings"] or out["transform_failures"] or out["other_failures"]:
        out["result"] = WARN
    return out


def _extend_capped(target: List[Any], items: Sequence[Any]) -> None:
    """Append while keeping at most :data:`MAX_REPORTED_FAILURES` entries."""
    for item in items:
        if len(target) >= MAX_REPORTED_FAILURES:
            return
        target.append(item)


def _existing_keys(
    rows: Sequence[RowMapping], key_lookup: Optional[KeyLookup]
) -> Dict[Tuple[str, str], Optional[Set[str]]]:
    """Which merge keys the graph already has, per ``(label, key_property)``.

    Grouped so one label costs one read rather than one per row. A group whose
    lookup could not answer maps to None, which the preview shows as unknown —
    the distinction that matters is between "would create" and "would merge", and
    inventing either from a failed read would be a guess presented as a fact.
    """
    groups: Dict[Tuple[str, str], List[Any]] = {}
    for row in rows:
        for node in row.nodes:
            groups.setdefault((node.label, node.key_property), []).append(node.key_value)

    if key_lookup is None:
        return {group: None for group in groups}

    found: Dict[Tuple[str, str], Optional[Set[str]]] = {}
    for (label, key_property), values in groups.items():
        found[(label, key_property)] = key_lookup(label, key_property, values)
    return found


def _node_state(node: Any, existing: Mapping[Tuple[str, str], Optional[Set[str]]]) -> str:
    """``'merge'``, ``'new'`` or ``'unknown'`` for one resolved node."""
    known = existing.get((node.label, node.key_property))
    if known is None:
        return "unknown"
    return "merge" if str(node.key_value) in known else "new"


def _preview_line(
    row: RowMapping, existing: Mapping[Tuple[str, str], Optional[Set[str]]]
) -> str:
    """One line saying what this row would write.

    ``Row 1 → Project(CAC-2024-0042) [new], Person(jane@mit.edu) [merge] → PI_OF``

    Row numbers are 1-based throughout this report — the first data row is "row
    1", as it is in the spreadsheet the user is looking at. The engine counts from
    zero, so its own ``row N:`` prefix is stripped from any message shown here
    rather than leaving two numbers for the same row on one line.
    """
    number = row.row_index + 1
    if row.skipped:
        return f"Row {number} → skipped: {row.skip_reason or 'rejected by row_filter'}"
    if not row.nodes:
        reason = _ROW_PREFIX_RE.sub("", row.errors[0]) if row.errors else "no node resolved"
        return f"Row {number} → nothing to write: {reason}"

    nodes = ", ".join(
        f"{node.label}({node.key_value}) [{_node_state(node, existing)}]"
        for node in row.nodes
    )
    line = f"Row {number} → {nodes}"

    types: List[str] = []
    for rel in row.relationships:
        rel_type = str(rel.get("type") or "")
        if rel_type and rel_type not in types:
            types.append(rel_type)
    if types:
        line += " → " + ", ".join(types)
    return line


def _classify_row_errors(
    row: RowMapping, property_columns: Mapping[str, Mapping[str, Sequence[str]]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split one row's engine errors into transform, key and everything else.

    Returns:
        ``(transform_failures, key_failures, other)``. Each entry has a 1-based
        ``row``, the offending ``column`` where it could be attributed to one, and
        the engine's message with its own row prefix removed.
    """
    transform: List[Dict[str, Any]] = []
    keys: List[Dict[str, Any]] = []
    other: List[Dict[str, Any]] = []
    number = row.row_index + 1

    for message in row.errors:
        text = _ROW_PREFIX_RE.sub("", message)
        if any(marker in message for marker in _KEY_FAILURE_MARKERS):
            keys.append({"row": number, "error": text})
            continue

        match = _PROPERTY_ERROR_RE.match(message) or _REQUIRED_EMPTY_RE.match(message)
        if match is None:
            other.append({"row": number, "error": text})
            continue

        mapping_id, prop = match.group(2), match.group(3)
        columns = _columns_for(property_columns, mapping_id, prop)
        transform.append({
            "row": number,
            "column": ", ".join(columns) if columns else None,
            "property": f"{mapping_id}.{prop}",
            "error": text,
        })
    return transform, keys, other


def _columns_for(
    property_columns: Mapping[str, Mapping[str, Sequence[str]]],
    mapping_id: str,
    prop: str,
) -> List[str]:
    """Columns feeding one property of one node mapping, for a failure report.

    ``source``/``source.fallback`` name the shared column of the
    transform-per-node form rather than a declared property, and in that form
    every property is fed by the same column — so the union is the answer.
    """
    per_property = property_columns.get(mapping_id) or {}
    if prop in per_property:
        return list(per_property[prop])
    if prop in _SOURCE_PSEUDO_PROPERTIES:
        shared: List[str] = []
        for columns in per_property.values():
            for column in columns:
                if column not in shared:
                    shared.append(column)
        return shared
    return []


def _reproducible(
    runner: PipelineRunner,
    prior: Optional[PriorRun],
    columns: List[str],
    row_count: Optional[int],
    interoperable: Mapping[str, Any],
) -> Dict[str, Any]:
    """The R step: has anything drifted since the last successful run?

    Never fails. A drifted source is still ingestible — what R owes the user is
    the warning that this run will not produce what the last one did. A source
    with no history passes trivially, because there is nothing it could differ
    from.
    """
    out: Dict[str, Any] = {"result": PASS, "warnings": []}
    if prior is None:
        out["note"] = "no prior run to compare"
        return out

    out["compared_to"] = {"ran_at": prior.ran_at, "pipeline_id": prior.pipeline_id}
    summary = prior.summary

    # Row count. The prior figure is the estimate find() reported then, falling
    # back to what the run actually read — the task block names
    # steps_json[0].summary.total_rows, which no run report has ever written.
    prior_rows = summary.get("row_count_estimate")
    if not prior_rows:
        prior_rows = summary.get("rows_read")
    if prior_rows and row_count:
        drift = abs(int(row_count) - int(prior_rows)) / int(prior_rows)
        if drift > ROW_COUNT_DRIFT_WARN:
            out["warnings"].append(
                f"the source has {row_count} rows; the last successful run saw "
                f"{prior_rows} ({drift:.0%} change)"
            )

    # Column set. The prior run recorded the columns the source had, not the
    # mapping it used, so what can be compared — and what actually matters — is a
    # column that was there last time, is mapped now, and has since disappeared.
    prior_columns = {str(c) for c in (summary.get("columns") or [])}
    if prior_columns:
        try:
            mapped = runner.engine.mapped_columns()
        except Exception as e:  # noqa: BLE001 - a config problem is I's to report
            logger.debug("Could not list mapped columns for the R comparison: %s", e)
            mapped = set()
        gone = sorted((prior_columns & mapped) - set(columns))
        if gone:
            out["warnings"].append(
                f"column(s) {', '.join(repr(c) for c in gone)} were present at the "
                "last successful run and are mapped, but the source no longer has them"
            )

    # Key resolution rate. The prior run reported whole-source counts and this is
    # a sample, so the comparison is between rates, and only a rate that got worse
    # is worth saying anything about.
    prior_read = int(summary.get("rows_read") or 0)
    if prior_read:
        prior_rate = (int(summary.get("rows_skipped") or 0)
                      + int(summary.get("rows_with_errors") or 0)) / prior_read
        now_rate = float(interoperable.get("key_failure_ratio") or 0.0)
        if now_rate > prior_rate:
            out["warnings"].append(
                f"{now_rate:.0%} of sampled rows fail key resolution, against "
                f"{prior_rate:.0%} of rows at the last successful run"
            )

    if out["warnings"]:
        out["result"] = WARN
    return out
