"""Collections: a purpose-built grouping for sharing and analysis.

``(:Collection)-[:INCLUDES]->(Dataset | Folder | File | context node)``

A Collection is its own level, above Dataset. It is the unit that gets a sharing
plan (and later an RO-Crate). Everything here is graph MERGE: nothing is deleted,
and ``files.db`` is only ever read through the Scans tab's read-only opener.

Members, by kind:

* ``dataset`` — a dataset recognized in a scan. Joins **by reference**: a
  ``:Dataset`` keyed on ``(scan_id, root_path)`` carrying the profile, file count
  and bytes. Its file rows are never copied into the graph.
* ``folder`` / ``file`` — ``:Folder`` / ``:File`` keyed on ``(path, host)``.
* ``context`` — an existing node (typically Request, Study, Sample, SampleType,
  Investigator, Lab) matched by element id and label. Never created here.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

#: The context nodes a collection is built for. Any existing node may be included;
#: these are the ones the sharing plan knows how to describe.
CONTEXT_LABELS = ('Request', 'Study', 'Sample', 'SampleType', 'Investigator', 'Lab')
KINDS = ('dataset', 'folder', 'file', 'context')
MAX_MEMBERS = 5_000

#: Property keys tried, in order, as a short display handle for a context node.
#: Investigators are people: they are only ever counted, never listed.
_DISPLAY_KEYS = ('uid', 'id', 'name', 'title', 'label')
_PUBLIC_LINK_KEYS = ('Link_PrimaryData', 'link_primarydata', 'Link_primarydata')
_REPOSITORIES = (('ImmPort', 'immport'), ('Zenodo', 'zenodo'), ('GEO', 'ncbi.nlm.nih.gov/geo'),
                 ('Figshare', 'figshare'), ('Dryad', 'datadryad'))
_URL = re.compile(r'https?://[^\s,;"\'<>]+', re.I)


def _text(value: Any) -> str:
    return str(value if value is not None else '').strip()


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalise_members(raw: Any, host_for) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Request members as ``{kind: [row, ...]}`` plus complaints.

    ``host_for(entry)`` returns the host label for a file/folder entry, or ''.
    """
    out: Dict[str, List[Dict[str, Any]]] = {k: [] for k in KINDS}
    problems: List[str] = []
    seen = set()
    for i, entry in enumerate(raw or []):
        if not isinstance(entry, dict):
            problems.append(f'members[{i}] is not an object')
            continue
        kind = _text(entry.get('kind')).lower()
        if kind == 'dataset':
            scan_id, root = _text(entry.get('scan_id')), _text(entry.get('root_path'))
            if not scan_id or not root:
                problems.append(f'members[{i}] (dataset) needs scan_id and root_path')
                continue
            key = (kind, scan_id, root)
            if key in seen:
                continue
            seen.add(key)
            out['dataset'].append({
                'scan_id': scan_id, 'root_path': root,
                'name': _text(entry.get('name')) or root.rstrip('/').rsplit('/', 1)[-1] or root,
                'profile': _text(entry.get('profile')) or None,
                'file_count': _int(entry.get('file_count')), 'bytes': _int(entry.get('bytes')),
            })
        elif kind in ('folder', 'file'):
            path = _text(entry.get('path'))
            name = _text(entry.get('name')) or path.rstrip('/').rsplit('/', 1)[-1]
            if not path:
                problems.append(f'members[{i}] ({kind}) has no path')
                continue
            host = host_for(entry)
            if not host:
                problems.append(f'members[{i}] ({kind} {name}) has no host to place it on')
                continue
            key = (kind, path, host)
            if key in seen:
                continue
            seen.add(key)
            row = {'path': path, 'name': name, 'host': host, 'size': _int(entry.get('size'))}
            out[kind].append(row)
        elif kind == 'context':
            label, node_id = _text(entry.get('label')), _text(entry.get('id'))
            if not label:
                problems.append(f'members[{i}] (context) has no label')
                continue
            if not node_id:
                problems.append(f'members[{i}] (context {label}) has no id')
                continue
            key = (kind, node_id)
            if key in seen:
                continue
            seen.add(key)
            out['context'].append({'label': label, 'id': node_id})
        else:
            problems.append(f'members[{i}] has unknown kind "{kind}"')
    return out, problems


def member_count(members: Dict[str, List[Any]]) -> int:
    return sum(len(v) for v in members.values())


def find_by_name(client, name: str) -> List[Dict[str, Any]]:
    return client.execute_read(
        "MATCH (c:Collection {name: $name}) "
        "OPTIONAL MATCH (c)-[:INCLUDES]->(m) "
        "RETURN c.id AS id, count(m) AS members",
        {'name': name},
    )


def save_collection(client, *, name: str, description: Optional[str], created_by: str,
                    members: Dict[str, List[Dict[str, Any]]], collection_id: Optional[str] = None) -> Dict[str, Any]:
    """MERGE the Collection and its INCLUDES edges. Returns counts by kind."""
    cid = collection_id or uuid.uuid4().hex
    client.execute_write(
        "MERGE (c:Collection {id: $id}) "
        "ON CREATE SET c.name = $name, c.created_by = $created_by, c.created_at = timestamp() "
        "SET c.description = coalesce($description, c.description), c.updated_at = timestamp()",
        {'id': cid, 'name': name, 'created_by': created_by, 'description': description or None},
    )
    linked: Dict[str, int] = {k: 0 for k in KINDS}
    if members['dataset']:
        # By reference: the (scan_id, root_path) Dataset carries the summary; no file rows.
        rows = client.execute_write(
            "MATCH (c:Collection {id: $id}) UNWIND $rows AS row "
            "MERGE (d:Dataset {scan_id: row.scan_id, root_path: row.root_path}) "
            "  ON CREATE SET d.name = row.name "
            "SET d.profile = coalesce(row.profile, d.profile), "
            "    d.file_count = coalesce(row.file_count, d.file_count), "
            "    d.bytes = coalesce(row.bytes, d.bytes), d.source = 'files.db' "
            "MERGE (c)-[:INCLUDES]->(d) RETURN count(d) AS linked",
            {'id': cid, 'rows': members['dataset']},
        )
        linked['dataset'] = int((rows[0].get('linked') if rows else 0) or 0)
    if members['folder']:
        rows = client.execute_write(
            "MATCH (c:Collection {id: $id}) UNWIND $rows AS row "
            "MERGE (f:Folder {path: row.path, host: row.host}) "
            "  ON CREATE SET f.name = row.name "
            "MERGE (c)-[:INCLUDES]->(f) RETURN count(f) AS linked",
            {'id': cid, 'rows': members['folder']},
        )
        linked['folder'] = int((rows[0].get('linked') if rows else 0) or 0)
    if members['file']:
        rows = client.execute_write(
            "MATCH (c:Collection {id: $id}) UNWIND $rows AS row "
            "MERGE (f:File {path: row.path, host: row.host}) "
            "  ON CREATE SET f.filename = row.name, f.size_bytes = row.size, f.stub = true "
            "MERGE (c)-[:INCLUDES]->(f) RETURN count(f) AS linked",
            {'id': cid, 'rows': members['file']},
        )
        linked['file'] = int((rows[0].get('linked') if rows else 0) or 0)
    if members['context']:
        rows = client.execute_write(
            "MATCH (c:Collection {id: $id}) UNWIND $rows AS row "
            "MATCH (n) WHERE elementId(n) = row.id AND row.label IN labels(n) "
            "MERGE (c)-[:INCLUDES]->(n) RETURN count(n) AS linked",
            {'id': cid, 'rows': members['context']},
        )
        linked['context'] = int((rows[0].get('linked') if rows else 0) or 0)
    return {'id': cid, 'linked': linked,
            'not_found': {k: len(members[k]) - linked[k] for k in KINDS if len(members[k]) > linked[k]}}


def list_collections(client) -> List[Dict[str, Any]]:
    return client.execute_read(
        "MATCH (c:Collection) OPTIONAL MATCH (c)-[:INCLUDES]->(m) "
        "RETURN c.id AS id, c.name AS name, c.description AS description, c.created_by AS created_by, "
        "c.created_at AS created_at, count(m) AS members ORDER BY c.created_at DESC LIMIT 200",
    )


# ── sharing plan ────────────────────────────────────────────────────────────

def _display(props: Dict[str, Any]) -> str:
    for key in _DISPLAY_KEYS:
        if props.get(key) not in (None, ''):
            return _text(props[key])[:80]
    return ''


def _repo_links(props: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(repository, url) pairs found in a Sample's Link_PrimaryData."""
    found: List[Tuple[str, str]] = []
    for key in _PUBLIC_LINK_KEYS:
        value = props.get(key)
        if value in (None, ''):
            continue
        for chunk in (value if isinstance(value, list) else [value]):
            for url in _URL.findall(_text(chunk)):
                lowered = url.lower()
                repo = next((name for name, needle in _REPOSITORIES if needle in lowered), 'Other')
                found.append((repo, url.rstrip('.)')))
    return found


def _extension(name: str) -> str:
    base = (name or '').rsplit('/', 1)[-1]
    return ('.' + base.rsplit('.', 1)[-1].lower()) if '.' in base.strip('.') else ''


def _dataset_types(scan_id: str, root: str) -> Tuple[Dict[str, List[int]], bool]:
    """File types of a recognized dataset from the read-only files.db, bounded in time.

    Returns ``({ext: [count, bytes]}, complete)``. Uses the Scans tab's opener, so
    files.db is only ever opened ``mode=ro``; nothing is written or created.
    """
    import time
    try:
        from ..web.routes import api_external_index as ex
        conn = ex._open()
    except Exception:  # noqa: BLE001 - no index configured/available: report, don't fail the plan
        return {}, False
    try:
        lo = root.rstrip('/') + '/'
        rows, capped = ex._timed(
            conn,
            "SELECT lower(coalesce(file_extension,'')) AS ext, count(*) AS c, sum(size) AS b "
            "FROM files INDEXED BY idx_files_path_prefix WHERE scan_id=? AND type='file' AND path>=? AND path<? "
            "GROUP BY ext", [scan_id, lo, lo[:-1] + '0'], time.monotonic() + 2.0, 5000)
    except Exception:  # noqa: BLE001
        return {}, False
    finally:
        conn.close()
    if capped:
        return {}, False
    return {(r['ext'] or ''): [int(r['c'] or 0), int(r['b'] or 0)] for r in rows}, True


def collection_summary(client, collection_id: str, *, dataset_types=_dataset_types) -> Dict[str, Any]:
    """Everything the sharing plan says, read from the graph. Counts and ids, bounded."""
    head = client.execute_read(
        "MATCH (c:Collection {id: $id}) RETURN c.name AS name, c.description AS description, "
        "c.created_by AS created_by, c.created_at AS created_at", {'id': collection_id})
    if not head:
        return {}
    members = client.execute_read(
        "MATCH (c:Collection {id: $id})-[:INCLUDES]->(m) "
        "RETURN elementId(m) AS eid, labels(m) AS labels, properties(m) AS p LIMIT $limit",
        {'id': collection_id, 'limit': MAX_MEMBERS})
    warnings: List[str] = []
    datasets, folders, files, context = [], [], [], []
    for row in members:
        labels, p = row.get('labels') or [], row.get('p') or {}
        if 'Dataset' in labels:
            datasets.append(p)
        elif 'Folder' in labels:
            folders.append(p)
        elif 'File' in labels:
            files.append(p)
        else:
            context.append((row.get('eid'), labels, p))
    if len(members) >= MAX_MEMBERS:
        warnings.append(f'Only the first {MAX_MEMBERS} members were summarized.')

    by_profile: Dict[str, Dict[str, int]] = {}
    types: Dict[str, List[int]] = {}
    storage: Dict[str, int] = {}
    total_files = total_bytes = 0
    unknown_size = 0
    for d in datasets:
        prof = by_profile.setdefault(_text(d.get('profile')) or '(no profile)', {'datasets': 0, 'files': 0, 'bytes': 0})
        prof['datasets'] += 1
        prof['files'] += int(d.get('file_count') or 0)
        prof['bytes'] += int(d.get('bytes') or 0)
        total_files += int(d.get('file_count') or 0)
        total_bytes += int(d.get('bytes') or 0)
        if d.get('bytes') is None:
            unknown_size += 1
        from ..web.routes.api_external_index import _classify
        host, share, _ = _classify(_text(d.get('root_path')))
        storage[f'{host or "(host unknown)"} / {share}'] = storage.get(f'{host or "(host unknown)"} / {share}', 0) + 1
        found, complete = dataset_types(_text(d.get('scan_id')), _text(d.get('root_path')))
        if not complete:
            warnings.append('File types of at least one recognized dataset could not be read from the scan index in time; '
                            'its files are counted but not broken down by type.')
        for ext, (c, b) in found.items():
            t = types.setdefault(ext, [0, 0])
            t[0] += c
            t[1] += b
    for f in files:
        total_files += 1
        size = f.get('size_bytes')
        if size is None:
            unknown_size += 1
        else:
            total_bytes += int(size)
        t = types.setdefault(_extension(_text(f.get('filename') or f.get('path'))), [0, 0])
        t[0] += 1
        t[1] += int(size or 0)
        storage[_text(f.get('host')) or '(host unknown)'] = storage.get(_text(f.get('host')) or '(host unknown)', 0) + 1
    for fo in folders:
        storage[_text(fo.get('host')) or '(host unknown)'] = storage.get(_text(fo.get('host')) or '(host unknown)', 0) + 1
    if folders:
        warnings.append(f'{len(folders)} folder(s) are included as folders; their contents are not enumerated in the totals.')
    if unknown_size:
        warnings.append(f'{unknown_size} member(s) have unknown size; byte totals include known sizes only.')

    ctx_counts: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []
    listed: Dict[str, List[str]] = {'Request': [], 'Study': [], 'SampleType': [], 'Lab': []}
    phi_props: Dict[str, set] = {}
    links: List[Dict[str, str]] = []
    ctx_ids = []
    for eid, labels, p in context:
        label = next((l for l in labels if l in CONTEXT_LABELS), labels[0] if labels else '?')  # first label otherwise
        ctx_counts[label] = ctx_counts.get(label, 0) + 1
        ctx_ids.append(eid)
        for key in p:
            phi_props.setdefault(label, set()).add(key)
        if label == 'Sample':
            samples.append({'eid': eid, 'handle': _display(p)})
            for repo, url in _repo_links(p):
                links.append({'repository': repo, 'url': url, 'sample': _display(p)})
        elif label in listed:
            listed[label].append(_display(p))

    # Neighbours of context members: the request/study a sample belongs to, its type.
    related: Dict[str, Dict[str, set]] = {'Request': {}, 'Study': {}, 'SampleType': {}}
    sample_types: Dict[str, int] = {}
    if ctx_ids:
        rows = client.execute_read(
            "UNWIND $ids AS id MATCH (m) WHERE elementId(m) = id "
            "OPTIONAL MATCH (m)-[r]-(x) WHERE any(l IN labels(x) WHERE l IN ['Request','Study','SampleType']) "
            "RETURN elementId(m) AS mid, labels(m) AS mlabels, labels(x) AS xlabels, properties(x) AS xp LIMIT 20000",
            {'ids': ctx_ids})
        per_sample_type: Dict[str, set] = {}
        for r in rows:
            xl = next((l for l in (r.get('xlabels') or []) if l in related), None)
            if not xl:
                continue
            handle = _display(r.get('xp') or {}) or '(unnamed)'
            related[xl].setdefault(handle, set()).add(r.get('mid'))
            if xl == 'SampleType' and 'Sample' in (r.get('mlabels') or []):
                per_sample_type.setdefault(handle, set()).add(r.get('mid'))
        sample_types = {k: len(v) for k, v in per_sample_type.items()}

    return {
        'id': collection_id,
        'name': head[0].get('name'), 'description': head[0].get('description'),
        'members': {'dataset': len(datasets), 'folder': len(folders), 'file': len(files), 'context': len(context)},
        'datasets_by_profile': by_profile,
        'total_files': total_files, 'total_bytes': total_bytes,
        'file_types': {k: v for k, v in types.items()},
        'storage_locations': storage,
        'context_counts': ctx_counts,
        'listed': {k: [x for x in v if x][:50] for k, v in listed.items()},
        'linked': {k: {h: len(ids) for h, ids in v.items()} for k, v in related.items()},
        'samples': {'count': len(samples), 'by_type': sample_types},
        'public_links': links,
        'property_names': {k: sorted(v) for k, v in phi_props.items()},
        'warnings': warnings,
    }


def collection_facts(summary: Dict[str, Any]):
    """Build the NIH DMS ``GraphFacts`` for a collection summary."""
    from plugins.nih_dms import config as cfg
    from plugins.nih_dms.graph_facts import FormatRow, GraphFacts, PHIHit

    formats = tuple(
        FormatRow(ext, c, b, cfg.FORMAT_STANDARDS.get(ext, ('Unclassified', None))[0],
                  cfg.FORMAT_STANDARDS.get(ext, ('Unclassified', None))[1])
        for ext, (c, b) in sorted(summary['file_types'].items(), key=lambda kv: (-kv[1][0], kv[0]))[:cfg.MAX_FORMATS])
    hits, seen = [], set()
    for label, props in summary.get('property_names', {}).items():
        for prop in props:
            if cfg.canonical_property(prop) in cfg.PHI_CANONICAL and (prop, label) not in seen:
                seen.add((prop, label))
                hits.append(PHIHit(prop, label, 'graph'))
    counts = [('Collection', 1)]
    if summary['members']['dataset']:
        counts.append(('Dataset', summary['members']['dataset']))
    if summary['members']['folder']:
        counts.append(('Folder', summary['members']['folder']))
    counts += sorted(summary['context_counts'].items())
    warnings = ('Collection scope only: the members of this one collection. No global graph, publication settings or schema scan was consulted. '
                'No PHI, consent or de-identification assessment has been performed.',
                *summary['warnings'])
    return GraphFacts(
        label_counts=tuple(counts), relationship_counts=(('INCLUDES', sum(summary['members'].values())),),
        file_count=summary['total_files'], file_bytes=summary['total_bytes'], formats=formats,
        phi_hits=tuple(hits), warnings=warnings)


def _human(n: int) -> str:
    v, unit = float(n or 0), 'B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB', 'PB'):
        if v < 1000 or unit == 'PB':
            break
        v /= 1000
    return f'{v:.0f} {unit}' if unit == 'B' else f'{v:.1f} {unit}'


def collection_section(summary: Dict[str, Any]) -> str:
    """The collection-specific part of the draft: what is in it, in plain lists."""
    m = summary['members']
    lines = [f'# Collection — sharing plan draft', '',
             f'**Collection:** {summary.get("name") or "(unnamed)"}  ',
             f'**Members:** {m["dataset"]} dataset(s), {m["folder"]} folder(s), {m["file"]} file(s), '
             f'{m["context"]} context record(s).', '',
             'Investigator review required. Not a compliance determination. '
             'This summary covers this collection only.', '', '## What the collection contains', '']
    if summary['datasets_by_profile']:
        lines += ['**Datasets by profile**', '']
        for prof, v in sorted(summary['datasets_by_profile'].items()):
            lines.append(f'- {prof}: {v["datasets"]} dataset(s), {v["files"]:,} files, {_human(v["bytes"])}')
        lines.append('')
    lines += [f'**Total files:** {summary["total_files"]:,}  ', f'**Total size:** {_human(summary["total_bytes"])}', '']
    if summary['file_types']:
        lines += ['**File types**', '']
        for ext, (c, b) in sorted(summary['file_types'].items(), key=lambda kv: (-kv[1][0], kv[0]))[:25]:
            lines.append(f'- {ext or "(no extension)"}: {c:,} files, {_human(b)}')
        lines.append('')
    if summary['storage_locations']:
        lines += ['**Storage locations**', '']
        for loc, n in sorted(summary['storage_locations'].items()):
            lines.append(f'- {loc}: {n} member(s)')
        lines.append('')
    if summary['context_counts']:
        lines += ['**Context records**', '']
        for label, n in sorted(summary['context_counts'].items()):
            lines.append(f'- {label}: {n}')
        lines.append('')
    for label in ('Request', 'Study'):
        names = summary['listed'].get(label) or []
        linked = summary['linked'].get(label) or {}
        if names or linked:
            lines += [f'**Linked {label.lower()}**', '']
            for h in names:
                lines.append(f'- {h} (included)')
            for h, n in sorted(linked.items()):
                lines.append(f'- {h} (linked from {n} included record(s))')
            lines.append('')
    if summary['samples']['count']:
        lines += [f'**Samples:** {summary["samples"]["count"]}', '']
        for t, n in sorted(summary['samples']['by_type'].items()):
            lines.append(f'- sample type {t}: {n}')
        lines.append('')
    if summary['public_links']:
        lines += ['**Public repository links (Sample.Link_PrimaryData)**', '']
        by_repo: Dict[str, List[Dict[str, str]]] = {}
        for link in summary['public_links']:
            by_repo.setdefault(link['repository'], []).append(link)
        for repo, items in sorted(by_repo.items()):
            urls = sorted({i['url'] for i in items})
            lines.append(f'- {repo}: {len(items)} sample(s) link to {len(urls)} record(s)')
            lines += [f'  - {u}' for u in urls[:20]]
        lines.append('')
    else:
        lines += ['**Public repository links:** none recorded on the included Samples.', '']
    lines += ['## PHI and consent', '',
              'This draft has not assessed protected health information, consent or de-identification. '
              'Confirm each member, especially investigator- and sample-level records, before sharing.', '']
    return '\n'.join(lines)


def collection_plan(summary: Dict[str, Any], fields: Dict[str, str]) -> str:
    """Collection section followed by the standard NIH DMS draft for the same facts."""
    from dataclasses import replace
    from plugins.nih_dms.generator import render_plan
    facts = replace(collection_facts(summary), repository=fields.get('repository'),
                    retention_years=fields.get('retention_years'), sharing_mode=fields.get('sharing_mode'),
                    access_contact=fields.get('access_contact'))
    return collection_section(summary) + '\n\n---\n\n' + render_plan(facts)
