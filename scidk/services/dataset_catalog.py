"""The Dataset catalog: one deterministic, searchable, paged list of Datasets.

Three kinds of entry share one list, each labelled with a state:

  candidate  recognized in a scan (external index ``data_objects``, read-only evidence); no graph node needed
  confirmed  a ``:Dataset {scan_id, root_path}`` in the graph, the editable human overlay on that evidence
  manual     a graph-only ``:Dataset {source:'manual'}`` made by hand from files and folders

This module is pure: it merges, filters, sorts and slices lists that the routes read (the scan index through its
read-only opener, the graph through the existing list query). It never opens a database and never writes.
Observed scanner facts (``pattern_name``/``profile``, counts, bytes) stay separate from human metadata
(``name`` when ``name_source == 'human'``, ``description``, ``human_profile``).
"""
import bisect
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

STATES = ('all', 'candidate', 'confirmed', 'manual')


def basename(path: Optional[str]) -> str:
    return (path or '').rstrip('/').rsplit('/', 1)[-1] or (path or '')


def matches(query: str, *fields: Any) -> bool:
    """Case-insensitive substring match of ``query`` against the identity fields; empty query matches all."""
    q = (query or '').strip().casefold()
    if not q:
        return True
    return q in ' '.join(str(f) for f in fields if f not in (None, '')).casefold()


def sort_key(item: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Global order: displayed name (case-insensitive), then root, scan and id so ties are deterministic."""
    return ((item.get('name') or '').casefold(), item.get('root_path') or '', item.get('scan_id') or '',
            item.get('dataset_id') or '')


def _graph_overlay(g: Dict[str, Any]) -> Dict[str, Any]:
    return {'dataset_id': g.get('id'), 'description': g.get('description'), 'human_profile': g.get('human_profile'),
            'name_is_human': g.get('name_source') == 'human', 'confirmed_at': g.get('confirmed_at'),
            'confirmed_by': g.get('confirmed_by'), 'updated_at': g.get('updated_at'),
            'human_edited_at': g.get('human_edited_at')}


def candidate_item(c: Dict[str, Any], g: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One scan candidate as a catalog item; ``g`` is its graph Dataset (makes it confirmed) or None."""
    item = {'key': '%s|%s' % (c['scan_id'], c['root_path']), 'state': 'confirmed' if g else 'candidate', 'name': c['name'],
            'root_path': c['root_path'], 'scan_id': c['scan_id'], 'in_index': True,
            'observed_profile': c.get('pattern_name'), 'file_count': c.get('file_count'),
            'total_bytes': c.get('total_bytes'), 'confidence': c.get('confidence'), 'host': c.get('host'),
            'share': c.get('share'), 'scan_root': c.get('scan_root'), 'scan_date': c.get('scan_date'),
            'dataset_id': None, 'description': None, 'human_profile': None, 'name_is_human': False,
            'confirmed_at': None}
    if g:
        item.update(_graph_overlay(g))
        item['name'] = g.get('name') or c['name']
    item['profile'] = item.get('human_profile') or item.get('observed_profile')
    return item


def build_items(candidates: Iterable[Dict[str, Any]], graph_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge scan candidates with graph Datasets; unsorted, one entry per (scan_id, root_path) or manual id."""
    graph = list(graph_rows)
    by_ref = {(g.get('scan_id'), g.get('root_path')): g for g in graph if g.get('scan_id') and g.get('root_path')}
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in candidates:
        ref = (c['scan_id'], c['root_path'])
        seen.add(ref)
        out.append(candidate_item(c, by_ref.get(ref)))
    for g in graph:
        if g.get('source') == 'manual':
            out.append({'key': 'manual|%s' % g.get('id'), 'state': 'manual', 'name': g.get('name') or '(unnamed)',
                        'root_path': None, 'scan_id': None, 'in_index': False, 'observed_profile': None,
                        'file_count': g.get('files'), 'folders': g.get('folders'), 'total_bytes': g.get('bytes'),
                        'host': None, 'share': None, 'scan_root': None, 'scan_date': None,
                        'created_at': g.get('created_at'), **_graph_overlay(g)})
        elif g.get('scan_id') and g.get('root_path') and (g['scan_id'], g['root_path']) not in seen:
            item = {'key': '%s|%s' % (g['scan_id'], g['root_path']), 'state': 'confirmed',
                    'name': g.get('name') or basename(g['root_path']), 'root_path': g['root_path'],
                    'scan_id': g['scan_id'], 'in_index': False, 'observed_profile': g.get('profile'),
                    'file_count': g.get('file_count'), 'total_bytes': g.get('dataset_bytes'), 'host': None,
                    'share': None, 'scan_root': None, 'scan_date': None}
            item.update(_graph_overlay(g))
            out.append(item)
    for item in out:
        item['profile'] = item.get('human_profile') or item.get('observed_profile')
    return out


def search_text(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (item.get('name'), item.get('root_path'), item.get('observed_profile'), item.get('human_profile'),
            item.get('host'), item.get('share'), item.get('scan_root'), item.get('dataset_id'))


def catalog_page(items: List[Dict[str, Any]], *, q: str = '', state: str = 'all', limit: int = 50,
                 offset: int = 0) -> Dict[str, Any]:
    """Filter by search text and state, sort globally by displayed name, then slice one page.

    ``counts`` are for the text-filtered set across all states, so the state filter can show what each holds."""
    state = state if state in STATES else 'all'
    found = [i for i in items if matches(q, *search_text(i))]
    counts = {k: 0 for k in STATES}
    counts['all'] = len(found)
    for i in found:
        counts[i['state']] += 1
    chosen = found if state == 'all' else [i for i in found if i['state'] == state]
    chosen.sort(key=sort_key)
    more = offset + limit < len(chosen)
    return {'total': len(chosen), 'counts': counts, 'offset': offset, 'limit': limit, 'state': state, 'q': q,
            'first': offset + 1 if chosen[offset:offset + limit] else 0,
            'last': offset + len(chosen[offset:offset + limit]), 'has_more': more,
            'next_offset': offset + limit if more else None,
            'prev_offset': max(0, offset - limit) if offset > 0 else None,
            'datasets': chosen[offset:offset + limit]}


# ── a cached, pre-sorted candidate list: browsing a very large index stays fast ──────────────────────────────

CANDIDATE_FIELDS = ('id', 'scan_id', 'pattern_name', 'root_path', 'file_count', 'total_bytes', 'confidence', 'status')


def _row_key(r) -> Tuple[str, str, str, str]:
    return (basename(r[3]).casefold(), r[3] or '', r[1] or '', '')


class CandidateSet:
    """Every scan candidate as tuples sorted once by (displayed name, root, scan); read-only after construction.

    Built from one read of the scan index and reused until the index file changes. A search is a substring scan over a
    precomputed text blob (root path, which ends in the name, plus profile) and the matching scans' host/share/root."""

    def __init__(self, rows: Iterable[Tuple], prov: Dict[str, Dict[str, Any]], make_entry: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]):
        self.prov, self._make_entry = prov, make_entry
        self.rows: List[Tuple] = sorted(rows, key=_row_key)
        self.blobs = [('%s\n%s' % (r[3] or '', r[2] or '')).casefold() for r in self.rows]
        self.pos = {(r[1], r[3]): i for i, r in enumerate(self.rows)}
        self.scan_text = {sid: ' '.join(str(p.get(k) or '') for k in ('scan_root', 'host', 'share')).casefold() for sid, p in prov.items()}

    def __len__(self) -> int:
        return len(self.rows)

    def entry(self, i: int) -> Dict[str, Any]:
        return self._make_entry(dict(zip(CANDIDATE_FIELDS, self.rows[i])), self.prov)

    def match(self, query: str, skip: Iterable[int] = ()) -> List[int]:
        """Row positions (in display order) whose text matches ``query``, leaving out the positions in ``skip``."""
        qf = (query or '').strip().casefold()
        skip = set(skip)
        if not qf:
            return [i for i in range(len(self.rows)) if i not in skip] if skip else list(range(len(self.rows)))
        hits = {sid for sid, t in self.scan_text.items() if qf in t}
        rows, blobs = self.rows, self.blobs
        return [i for i, b in enumerate(blobs) if (qf in b or rows[i][1] in hits) and i not in skip]


def cached_page(cands: CandidateSet, graph_rows: List[Dict[str, Any]], *, q: str = '', state: str = 'all',
                limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """The same page :func:`catalog_page` would give, without re-reading or re-sorting the candidates.

    Candidates that have a graph Dataset (confirmed) and manual Datasets are few: they are merged in at request time, so
    names, descriptions and state always come from the graph. Plain candidates are sliced straight from the sorted list."""
    state = state if state in STATES else 'all'
    refs = {(g.get('scan_id'), g.get('root_path')) for g in graph_rows if g.get('scan_id') and g.get('root_path')}
    skip = {cands.pos[r] for r in refs if r in cands.pos}
    special = build_items([cands.entry(cands.pos[r]) for r in refs if r in cands.pos], graph_rows)
    special = sorted((i for i in special if matches(q, *search_text(i))), key=sort_key)
    plain = cands.match(q, skip)
    counts = {'all': len(plain) + len(special), 'candidate': len(plain), 'confirmed': 0, 'manual': 0}
    for i in special:
        counts[i['state']] += 1
    if state == 'candidate':
        special = []
    elif state in ('confirmed', 'manual'):
        special, plain = [i for i in special if i['state'] == state], []
    total = len(plain) + len(special)
    end = min(total, offset + limit)
    # A special item's place in the merged order is its rank among the plain rows plus the specials before it.
    places = [bisect.bisect_left(plain, sort_key(i), key=lambda n: _row_key(cands.rows[n])) + j for j, i in enumerate(special)]
    page: List[Dict[str, Any]] = []
    for g in range(offset, end):
        k = bisect.bisect_left(places, g)
        if k < len(places) and places[k] == g:
            page.append(special[k])
        else:
            page.append(candidate_item(cands.entry(plain[g - k])))
    more = offset + limit < total
    return {'total': total, 'counts': counts, 'offset': offset, 'limit': limit, 'state': state, 'q': q,
            'first': offset + 1 if page else 0, 'last': offset + len(page), 'has_more': more,
            'next_offset': offset + limit if more else None, 'prev_offset': max(0, offset - limit) if offset > 0 else None,
            'datasets': page}
