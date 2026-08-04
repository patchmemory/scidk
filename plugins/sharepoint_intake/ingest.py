"""Ingest logic for the SharePoint Intake plugin.

Pulls a SharePoint intake list (exported to CSV and reachable via rclone) into
the SciDK knowledge graph as ``Project``, ``Person`` and ``Attachment`` nodes.

Design contract:
  * Config-driven - all column names and vocabularies live in ``config.py``.
  * Error-isolated - one bad row never aborts the run; it is recorded and skipped.
  * Idempotent - every write goes through ``Neo4jClient.write_declared_nodes``
    (MERGE on a key property), so re-running the same export converges.

Node model
  Project(project_id)  -- key: CACProtocol, else a deterministic fallback
  Person(email|name)   -- key: email when known, else display name
  Attachment(path|filename)

Relationships
  (Person)-[:SUBMITTED]->(Project)
  (Person)-[:PI_OF]->(Project)
  (Person)-[:COLLABORATES_ON]->(Project)
  (Project)-[:HAS_ATTACHMENT]->(Attachment)
"""
from __future__ import annotations

import csv
import io
import logging
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pandas as pd

from . import config as cfg
from . import parser

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 120.0

#: Rows :func:`scan_source` will count before giving up on an exact total, so
#: ``find()`` stays inside its 10s budget on an arbitrarily large list.
MAX_SCAN_ROWS = 100_000

_DELIMITERS = {".csv": ",", ".tsv": "\t", ".tab": "\t"}
_EXCEL_EXTS = (".xlsx", ".xlsm")


def get_provider(provider: Optional[Any] = None) -> Any:
    """Return ``provider``, or a fresh ``RcloneProvider`` when none was given.

    ``cat``/``open`` only shell out to rclone, so no ``initialize()`` is needed.
    """
    if provider is not None:
        return provider
    from scidk.core.providers import RcloneProvider

    return RcloneProvider()


def is_local_source(source: str) -> bool:
    """True when ``source`` names an existing local file rather than a remote."""
    return bool(source) and os.path.isfile(source)


def normalize_header(name: Any) -> str:
    """Collapse internal whitespace in a column header.

    e.g. ``"PI  Archived"`` -> ``"PI Archived"``. SharePoint exports are
    inconsistent about double spaces; mapping configs should not have to be.
    """
    return " ".join(str("" if name is None else name).split())


def _clean(value: Any) -> str:
    """Render a raw cell as a stripped string ("" for a missing value)."""
    return "" if value is None else str(value).strip()


def _decode(chunk: Any) -> str:
    """Decode a line of source bytes, tolerating a BOM and bad bytes."""
    if isinstance(chunk, str):
        return chunk
    return bytes(chunk).decode("utf-8-sig", errors="replace")


def source_extension(source: str) -> str:
    """Lowercased file extension of ``source`` ("" when it has none)."""
    return os.path.splitext(str(source or "").split("?", 1)[0])[1].lower()


def source_metadata(source: str, provider: Optional[Any] = None) -> Dict[str, Any]:
    """Describe the source without reading its contents.

    Uses ``os.stat`` for a local path and ``rclone lsjson`` for a remote one.
    Never raises: an unreachable listing just yields a sparser dict, because this
    is descriptive detail for the UI, not a precondition for reading.
    """
    if is_local_source(source):
        stat = os.stat(source)
        return {"transport": "local", "name": os.path.basename(source),
                "size": stat.st_size, "modified": stat.st_mtime}
    meta: Dict[str, Any] = {"transport": "rclone", "name": str(source).rsplit("/", 1)[-1]}
    try:
        entries = get_provider(provider).list_files(source, recursive=False) or []
    except Exception as e:  # noqa: BLE001 - listing is best-effort metadata
        logger.debug("lsjson on %r failed: %s", source, e)
        return meta
    files = [e for e in entries if not e.get("IsDir")]
    if len(files) == 1:
        meta.update({"name": files[0].get("Name") or meta["name"],
                     "size": files[0].get("Size"), "modified": files[0].get("ModTime")})
    elif files:
        meta["candidates"] = [e.get("Name") for e in files]
    return meta


def iter_lines(source: str, provider: Optional[Any] = None,
               timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> Iterator[str]:
    """Yield decoded text lines from ``source`` without buffering all of it.

    Local paths are read directly. Remote paths stream through the provider's
    ``open()`` (``rclone cat`` on a pipe). A provider that cannot stream falls
    back to a buffered ``cat()`` — correct, but no longer lazy, which is why the
    fallback is logged.

    Note: the streaming path has no timeout; ``timeout_sec`` applies only to the
    buffered fallback. Bounding a whole run is the Pipeline runner's job.
    """
    if is_local_source(source):
        with open(source, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            yield from fh
        return

    prov = get_provider(provider)
    stream = None
    try:
        stream = prov.open(source)
    except (AttributeError, NotImplementedError):
        stream = None
    if stream is None:
        logger.debug("Provider %s cannot stream; falling back to buffered cat", type(prov).__name__)
        yield from io.StringIO(_decode(prov.cat(source, timeout_sec=timeout_sec)), newline="")
        return
    try:
        for raw in stream:
            yield _decode(raw)
    finally:
        try:
            stream.close()
        except Exception:  # noqa: BLE001 - closing a spent pipe is not an error
            pass


def _dict_rows(columns: List[str], values_iter: Iterator[Any]) -> Iterator[Dict[str, str]]:
    """Zip successive value tuples against ``columns``, skipping blank lines.

    Values beyond the header width are dropped: the header is authoritative.
    """
    for values in values_iter:
        cleaned = [_clean(v) for v in values]
        if not any(cleaned):
            continue
        yield {col: val for col, val in zip(columns, cleaned) if col}


def _excel_rows(source: str, provider: Optional[Any], timeout_sec: float,
                sheet: Optional[str]) -> Tuple[List[str], Iterator[Dict[str, str]]]:
    """Open a workbook in openpyxl read-only mode and stream its first sheet.

    A remote workbook is buffered in memory first — an xlsx is a zip container
    and needs random access, so it cannot stream the way a CSV can.
    """
    from openpyxl import load_workbook

    handle: Any = source
    if not is_local_source(source):
        handle = io.BytesIO(get_provider(provider).cat(source, timeout_sec=timeout_sec))
    workbook = load_workbook(handle, read_only=True, data_only=True)
    worksheet = workbook[sheet] if sheet else workbook[workbook.sheetnames[0]]
    values = worksheet.iter_rows(values_only=True)
    columns = [normalize_header(c) for c in (next(values, ()) or ())]

    def _rows() -> Iterator[Dict[str, str]]:
        try:
            yield from _dict_rows(columns, values)
        finally:
            workbook.close()

    return columns, _rows()


def open_rows(source: str, provider: Optional[Any] = None,
              timeout_sec: float = DEFAULT_TIMEOUT_SEC,
              sheet: Optional[str] = None) -> Tuple[List[str], Iterator[Dict[str, str]]]:
    """Return ``(columns, lazy row iterator)`` for a source.

    Format follows the extension: ``.xlsx``/``.xlsm`` are read with openpyxl,
    ``.tsv``/``.tab`` are tab-delimited, anything else is comma-delimited.
    Returning the columns separately means a header-only source still reports its
    schema, and lets ``find()`` describe a source it never fully reads.
    """
    ext = source_extension(source)
    if ext in _EXCEL_EXTS:
        return _excel_rows(source, provider, timeout_sec, sheet)
    reader = csv.reader(
        iter_lines(source, provider=provider, timeout_sec=timeout_sec),
        delimiter=_DELIMITERS.get(ext, ","),
    )
    columns = [normalize_header(c) for c in next(reader, [])]
    return columns, _dict_rows(columns, reader)


def iter_rows(source: str, provider: Optional[Any] = None,
              timeout_sec: float = DEFAULT_TIMEOUT_SEC,
              sheet: Optional[str] = None) -> Iterator[Dict[str, str]]:
    """Stream ``source`` as raw ``{column: value}`` rows. No transforms applied."""
    _columns, rows = open_rows(source, provider=provider, timeout_sec=timeout_sec, sheet=sheet)
    yield from rows


def scan_source(source: str, provider: Optional[Any] = None,
                timeout_sec: float = DEFAULT_TIMEOUT_SEC,
                sample_rows: int = 3, max_scan_rows: int = MAX_SCAN_ROWS,
                sheet: Optional[str] = None) -> Dict[str, Any]:
    """Single lazy pass over ``source`` describing its schema and size.

    Retains only ``sample_rows`` rows, so memory stays flat however long the
    source is. Counting stops at ``max_scan_rows``, after which ``row_count`` is
    None and ``truncated`` is True rather than blowing the 10s ``find()`` budget.

    Returns ``{columns, sample, row_count, truncated}``.
    """
    columns, rows = open_rows(source, provider=provider, timeout_sec=timeout_sec, sheet=sheet)
    sample: List[Dict[str, str]] = []
    count = 0
    truncated = False
    for row in rows:
        if len(sample) < sample_rows:
            sample.append(dict(row))
        count += 1
        if count >= max_scan_rows:
            truncated = True
            break
    return {"columns": columns, "sample": sample,
            "row_count": None if truncated else count, "truncated": truncated}


def verify_read(source: str, provider: Optional[Any] = None,
                timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
    """Prove an authenticated data read of ``source`` is permitted.

    Reads the smallest possible slice of actual file content — distinct from a
    listing, which a credential may be allowed to see without being allowed to
    read the rows. Raises on failure; returns None on success.
    """
    if is_local_source(source):
        with open(source, "rb") as fh:
            fh.read(1)
        return
    get_provider(provider).cat(source, max_bytes=1, timeout_sec=timeout_sec)


def detect_auth_method(source: str) -> Optional[str]:
    """Best-effort identification of the credential type behind ``source``.

    Reads ``rclone config dump`` and reports ``"rclone_oauth"`` for a remote
    holding an OAuth token, ``"rclone_basic"`` for one configured with static
    credentials, and ``"local"`` for a plain local path. Returns None when it
    cannot tell — an unknown auth method is not a failure to report access.
    """
    if is_local_source(source):
        return "local"
    remote = str(source or "").split(":", 1)[0]
    if not remote or ":" not in str(source):
        return None
    try:
        import json
        import shutil
        import subprocess

        exe = shutil.which("rclone")
        if not exe:
            return None
        proc = subprocess.run([exe, "config", "dump"], capture_output=True, text=True, timeout=15)
        entry = (json.loads(proc.stdout or "{}") or {}).get(remote) or {}
    except Exception as e:  # noqa: BLE001 - identification is advisory only
        logger.debug("rclone config dump failed: %s", e)
        return None
    if not entry:
        return None
    return "rclone_oauth" if entry.get("token") else "rclone_basic"


# ---------------------------------------------------------------------------
# Legacy ETL — moves to scidk/pipeline/ in Cycle 3B; stripped in Cycle 3 Task B.
# ---------------------------------------------------------------------------


class SharePointIntakeIngest:
    """Orchestrates a single ingest run of a SharePoint intake CSV."""

    def __init__(self, provider: Optional[Any] = None, app: Optional[Any] = None):
        """
        Args:
            provider: An rclone provider exposing ``cat(target, timeout_sec=...) -> bytes``.
                      Defaults to a fresh ``RcloneProvider`` (cat only shells out to
                      rclone, so no ``initialize()`` is required).
            app: Optional Flask app, used only to resolve Neo4j connection params.
        """
        self._app = app
        if provider is None:
            from scidk.core.providers import RcloneProvider
            provider = RcloneProvider()
        self._provider = provider

    # ------------------------------------------------------------------ I/O

    def _load_csv_bytes(self, source: str, timeout_sec: float = 120.0) -> bytes:
        """Return the raw CSV bytes for ``source``.

        A ``source`` that resolves to an existing local file is read directly;
        anything else is treated as an rclone remote path (``remote:path``).
        """
        if source and os.path.isfile(source):
            with open(source, "rb") as fh:
                return fh.read()
        return self._provider.cat(source, timeout_sec=timeout_sec)

    def _read_dataframe(self, csv_bytes: bytes) -> pd.DataFrame:
        """Parse CSV bytes into a normalized, all-string DataFrame.

        ``keep_default_na=False`` keeps blanks as ``""`` (never NaN) so the pure
        resolvers in ``parser`` can rely on ``.strip()`` semantics. Headers have
        internal whitespace collapsed to match ``FIELD_MAP`` keys.
        """
        df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)
        df = df.rename(columns=parser.normalize_columns(df.columns))
        return df

    def load_vocabulary(self) -> Dict[str, List[str]]:
        """Load the controlled vocabulary, falling back to the built-in default.

        The external source (``SETTING_VOCAB_PATH``) is expected to be a CSV whose
        column headers are entity field names and whose column values are the
        allowed terms. Any failure to read/parse it falls back silently to
        ``DEFAULT_VOCABULARY`` - vocabulary is a soft consistency check.
        """
        path = cfg.get_config_value(cfg.SETTING_VOCAB_PATH, cfg.ENV_VOCAB_PATH)
        if not path:
            return dict(cfg.DEFAULT_VOCABULARY)
        try:
            raw = self._load_csv_bytes(path, timeout_sec=60.0)
            vdf = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
            vocab: Dict[str, List[str]] = {}
            for col in vdf.columns:
                terms = [t.strip() for t in vdf[col].tolist() if t and t.strip()]
                if terms:
                    vocab[str(col).strip()] = terms
            return vocab or dict(cfg.DEFAULT_VOCABULARY)
        except Exception as e:  # noqa: BLE001 - soft check; never block ingest
            logger.warning("Vocabulary source %r unreadable (%s); using defaults", path, e)
            return dict(cfg.DEFAULT_VOCABULARY)

    # -------------------------------------------------------- declarations

    @staticmethod
    def _person_decl(person: Dict[str, Optional[str]]) -> Optional[Tuple[Dict, Dict, Tuple]]:
        """Build a Person node declaration + match dict from a resolved person.

        Returns ``(node_decl, match_dict, dedup_key)`` or None when the person
        has neither email nor name. Keys by email when present (stable identity),
        else by display name.
        """
        email = (person.get("email") or "").strip().lower() or None
        name = (person.get("name") or "").strip() or None
        if email:
            props: Dict[str, Any] = {"email": email}
            if name:
                props["name"] = name
            return (
                {"label": "Person", "key_property": "email", "properties": props},
                {"email": email},
                ("email", email),
            )
        if name:
            return (
                {"label": "Person", "key_property": "name", "properties": {"name": name}},
                {"name": name},
                ("name", name),
            )
        return None

    def _build_project_props(self, row: Dict[str, str], index: int) -> Dict[str, Any]:
        """Assemble the Project node properties for one row (config-driven)."""
        props: Dict[str, Any] = {"project_id": parser.resolve_project_id(row, index)}

        # Plain single-column fields copied straight through when non-empty.
        for field in cfg.PLAIN_PROJECT_FIELDS:
            val = parser._col(row, field)
            if val:
                props[field] = val

        # _sp / _orig variants (prefer current SharePoint value).
        for project_prop, sp_key, orig_key in cfg.SP_ORIG_FIELDS:
            resolved = parser.resolve_sp_orig(row, sp_key, orig_key)
            if resolved:
                props[project_prop] = resolved

        return props

    def build_declarations(
        self, df: pd.DataFrame, vocabulary: Dict[str, List[str]]
    ) -> Tuple[List[Dict], List[Dict], List[Dict], List[str]]:
        """Turn a DataFrame into node/relationship declarations.

        Returns ``(nodes, relationships, errors, vocab_warnings)``. Nodes are
        de-duplicated by (label, key). Each ``errors`` entry is
        ``{"row": <index>, "error": <message>}``.
        """
        nodes: List[Dict] = []
        relationships: List[Dict] = []
        errors: List[Dict] = []
        vocab_warnings: List[str] = []

        seen_nodes: set = set()

        def _add_node(decl: Dict, dedup_key: Tuple) -> None:
            if dedup_key in seen_nodes:
                return
            seen_nodes.add(dedup_key)
            nodes.append(decl)

        for index, raw_row in enumerate(df.to_dict(orient="records")):
            row = {k: (v if v is not None else "") for k, v in raw_row.items()}
            try:
                if not parser.has_project_identity(row):
                    raise ValueError("row has neither CACProtocol nor ShortDescription")

                project_props = self._build_project_props(row, index)
                project_id = project_props["project_id"]
                project_match = {"project_id": project_id}
                _add_node(
                    {"label": "Project", "key_property": "project_id", "properties": project_props},
                    ("Project", project_id),
                )

                # Vocabulary consistency (soft warnings, scoped to this project).
                for w in parser.check_controlled_vocab(project_props, vocabulary):
                    vocab_warnings.append(f"[{project_id}] {w}")

                # Submitter -> SUBMITTED.
                submitter = self._person_decl(parser.resolve_submitter(row))
                if submitter:
                    decl, match, key = submitter
                    _add_node(decl, ("Person",) + key)
                    relationships.append({
                        "type": "SUBMITTED", "from_label": "Person", "from_match": match,
                        "to_label": "Project", "to_match": project_match,
                    })

                # PI -> PI_OF.
                pi = parser.resolve_pi(row)
                pi_decl = self._person_decl(pi) if pi else None
                if pi_decl:
                    decl, match, key = pi_decl
                    _add_node(decl, ("Person",) + key)
                    relationships.append({
                        "type": "PI_OF", "from_label": "Person", "from_match": match,
                        "to_label": "Project", "to_match": project_match,
                    })

                # Collaborators -> COLLABORATES_ON.
                for collab in parser.resolve_collaborators(row):
                    collab_decl = self._person_decl(collab)
                    if not collab_decl:
                        continue
                    decl, match, key = collab_decl
                    _add_node(decl, ("Person",) + key)
                    relationships.append({
                        "type": "COLLABORATES_ON", "from_label": "Person", "from_match": match,
                        "to_label": "Project", "to_match": project_match,
                    })

                # Attachment -> HAS_ATTACHMENT (only when actually copied).
                attachment = parser.resolve_attachment(row)
                if attachment and attachment.get("status") == "available":
                    att_key = attachment.get("path") or attachment.get("filename")
                    if att_key:
                        key_prop = "path" if attachment.get("path") else "filename"
                        _add_node(
                            {"label": "Attachment", "key_property": key_prop,
                             "properties": {k: v for k, v in attachment.items() if v}},
                            ("Attachment", att_key),
                        )
                        relationships.append({
                            "type": "HAS_ATTACHMENT", "from_label": "Project", "from_match": project_match,
                            "to_label": "Attachment", "to_match": {key_prop: att_key},
                        })

            except Exception as e:  # noqa: BLE001 - per-row error isolation
                errors.append({"row": index, "error": str(e)})

        return nodes, relationships, errors, vocab_warnings

    # ---------------------------------------------------------------- write

    def _write(self, nodes: List[Dict], relationships: List[Dict]) -> Dict[str, Any]:
        """Write declarations to Neo4j; raises if the connection is unconfigured."""
        from scidk.services.neo4j_client import Neo4jClient, get_neo4j_params

        uri, user, password, database, auth_mode = get_neo4j_params(self._app)
        if not uri:
            raise RuntimeError("Neo4j not configured. Configure a connection in Settings.")
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            return client.write_declared_nodes(nodes, relationships)
        finally:
            client.close()

    # --------------------------------------------------------------- public

    def run(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a full ingest run.

        Args:
            config: instance configuration. Recognized keys:
                - ``source`` / ``file_path``: rclone remote path or local CSV path.
                  Falls back to ``SETTING_SYNC_REMOTE`` / env when omitted.
                - ``dry_run``: when True, build declarations but do not write.
                - ``timeout_sec``: rclone cat timeout (default 120).

        Returns a summary dict; never raises for row-level problems.
        """
        source = (config.get("source") or config.get("file_path") or "").strip()
        if not source:
            source = cfg.get_config_value(cfg.SETTING_SYNC_REMOTE, cfg.ENV_SYNC_REMOTE) or ""
        if not source:
            return {
                "status": "error",
                "message": "No source configured. Set 'source' or "
                           f"the '{cfg.SETTING_SYNC_REMOTE}' setting / {cfg.ENV_SYNC_REMOTE} env var.",
            }

        dry_run = bool(config.get("dry_run", False))
        timeout_sec = float(config.get("timeout_sec", 120.0))

        try:
            csv_bytes = self._load_csv_bytes(source, timeout_sec=timeout_sec)
            df = self._read_dataframe(csv_bytes)
        except Exception as e:  # noqa: BLE001 - source/parse failure is fatal for the run
            logger.error("Failed to load SharePoint intake source %r: %s", source, e)
            return {"status": "error", "message": f"Failed to load source: {e}", "source": source}

        vocabulary = self.load_vocabulary()
        nodes, relationships, errors, vocab_warnings = self.build_declarations(df, vocabulary)

        summary: Dict[str, Any] = {
            "status": "success",
            "source": source,
            "rows_total": int(len(df)),
            "rows_failed": len(errors),
            "declared_nodes": len(nodes),
            "declared_relationships": len(relationships),
            "errors": errors,
            "vocab_warnings": vocab_warnings,
            "dry_run": dry_run,
        }

        if dry_run:
            summary["message"] = (
                f"Dry run: {len(nodes)} nodes / {len(relationships)} relationships "
                f"from {len(df)} rows ({len(errors)} row errors)."
            )
            return summary

        try:
            write_result = self._write(nodes, relationships)
        except Exception as e:  # noqa: BLE001 - surface connection/write failure
            logger.error("SharePoint intake write failed: %s", e)
            summary["status"] = "error"
            summary["message"] = f"Write failed: {e}"
            return summary

        summary["written_nodes"] = write_result.get("written_nodes", 0)
        summary["written_relationships"] = write_result.get("written_relationships", 0)
        summary["write_errors"] = write_result.get("errors", [])
        summary["message"] = (
            f"Ingested {summary['written_nodes']} nodes / "
            f"{summary['written_relationships']} relationships from {len(df)} rows "
            f"({len(errors)} row errors, {len(vocab_warnings)} vocab warnings)."
        )
        return summary


def run_ingest(config: Dict[str, Any], provider: Optional[Any] = None, app: Optional[Any] = None) -> Dict[str, Any]:
    """Module-level convenience wrapper around :class:`SharePointIntakeIngest`."""
    return SharePointIntakeIngest(provider=provider, app=app).run(config)
