"""Bounded deterministic projections, trusted-local builders and disclosure boundary.

Builders are internal administration APIs, not self-authorizing agent readers.
Source bindings are supplied by trusted deployment configuration, never a request.
"""
import ast
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import subprocess

from scidk.curation.contracts import ContractError, canonical, digest
from scidk.agent_tools.security import PolicyStore, REFUSAL, DisclosureDenied

EDGE_TYPES = {'DOCUMENTED_BY', 'IMPLEMENTED_BY', 'EXPOSED_VIA', 'REQUIRES', 'VALIDATED_BY',
              'HAS_PROPERTY', 'DECLARES', 'SOURCE_LABEL', 'TARGET_LABEL'}


def content_hash(data):
    return 'sha256:' + sha256(data).hexdigest()


def source_state(root, source):
    """Only manifest-selected repository files; refuse traversal/symlink escapes."""
    path = (Path(root) / source['path']).resolve()
    if Path(source['path']).is_absolute() or not path.is_relative_to(Path(root).resolve()):
        raise ContractError('Source must be inside repository')
    try:
        data = path.read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return {'hash': None, 'valid': False}
    valid = True
    if source.get('symbol'):
        # AST declarations, never substring matches or imports of selected code.
        tree = ast.parse(data)
        symbols = {n.name for n in ast.walk(tree)
                   if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
        valid = source['symbol'] in symbols
    if source.get('section'):
        valid = valid and source['section'] in {
            line.lstrip('#').strip() for line in data.decode().splitlines() if line.startswith('#')}
    return {'hash': content_hash(data), 'valid': valid}


class Projection:
    def __init__(self, nodes, edges, metadata=None):
        nodes = deepcopy(nodes)
        self._nodes = {node['id']: node for node in nodes}
        if len(nodes) != len(self._nodes) or len(nodes) > 512:
            raise ContractError('Duplicate or excessive projection nodes')
        self._edges = sorted(deepcopy(edges), key=canonical)
        if len(self._edges) > 4096:
            raise ContractError('Excessive projection edges')
        for edge in self._edges:
            if (set(edge) != {'source', 'type', 'target'} or edge['type'] not in EDGE_TYPES or
                    edge['source'] not in self._nodes or edge['target'] not in self._nodes):
                raise ContractError('Invalid projection edge')
        self._metadata = deepcopy(metadata or {})
        self.version = digest('projection', self.snapshot())

    def snapshot(self):
        return deepcopy({'nodes': sorted(self._nodes.values(), key=lambda n: n['id']),
                         'edges': self._edges, 'metadata': self._metadata})

    def traverse(self, start, *, depth=3, limit=128):
        """Trusted-local outgoing BFS. Never return an incomplete authorization set."""
        if type(depth) is not int or not 0 <= depth <= 6 or type(limit) is not int or not 1 <= limit <= 256:
            raise ContractError('Invalid traversal bounds')
        if start not in self._nodes:
            raise ContractError('Unknown entry')
        seen, frontier = {start}, {start}
        for _ in range(depth):
            frontier = {e['target'] for e in self._edges if e['source'] in frontier} - seen
            seen |= frontier
            if len(seen) > limit:
                raise ContractError('Traversal exceeds bound')
        return deepcopy({'version': self.version, 'nodes': [self._nodes[k] for k in sorted(seen)],
                         'edges': [e for e in self._edges if e['source'] in seen and e['target'] in seen],
                         'metadata': self._metadata})

    def compare(self, current):
        """Snapshot freshness, including SQLite/external sources without file IO."""
        before, after = self._nodes, current._nodes
        return [{'id': id, 'reason': 'projection_entry_changed_or_missing'}
                for id in sorted(set(before) | set(after)) if before.get(id) != after.get(id)]

    def freshness(self, root, *, revision, applicability):
        warnings = []
        for node in sorted(self._nodes.values(), key=lambda n: n['id']):
            for source in node.get('sources', []):
                try:
                    state = source_state(root, source)
                    if not state['valid'] or state['hash'] != source['hash']:
                        warnings.append({'id': node['id'], 'reason': 'source_changed_or_missing'})
                except (ValueError, SyntaxError, OSError, UnicodeError):
                    warnings.append({'id': node['id'], 'reason': 'source_unreadable'})
            if node.get('git_revision') != revision:
                warnings.append({'id': node['id'], 'reason': 'git_revision_changed'})
            if node.get('applicability') != applicability:
                warnings.append({'id': node['id'], 'reason': 'applicability_changed'})
        return warnings


def git_revision(root):
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()


def system_projection(root, bindings=None, *, revision=None, applicability='knowledge-context/1'):
    from .system_manifest import ENTRIES, EDGES
    revision = revision or git_revision(root)
    nodes = []
    for entry in ENTRIES:
        node = deepcopy(entry)
        source = {k: node.pop(k) for k in ('path', 'symbol', 'section') if k in node}
        state = source_state(root, source)
        source.update(hash=state['hash'], valid=state['valid'],
                      source_scope=deepcopy((bindings or {}).get(node['id'])))
        node.update(sources=[source], git_revision=revision, applicability=applicability,
                    visibility='restricted', source_scope=deepcopy((bindings or {}).get(node['id'])))
        nodes.append(node)
    return Projection(nodes, EDGES, {'domain': 'system', 'generated': True})


class ContextService:
    """Default-off, internal service. Identity/bindings originate at trusted adapters.

    All-or-nothing disclosure: validate every traversed node and metadata before
    returning IDs, paths, edges, revision, diagnostics or definitions. Restricted
    metadata uses Stage 3 evidence grants keyed by immutable context digest.
    """
    def __init__(self, projection, settings_db, *, enabled=False):
        self.projection, self.policy, self.enabled = projection, PolicyStore(settings_db), enabled

    @staticmethod
    def grant_id(node):
        return digest('context', node)

    def read(self, start, identity, *, depth=3, limit=128):
        try:
            if not self.enabled:
                raise DisclosureDenied()
            with self.policy.resolve(identity) as policy:
                result = self.projection.traverse(start, depth=depth, limit=limit)
                # Global conflict metadata can reference other sources. Authorize
                # every projection node before disclosing such diagnostics.
                checked = (self.projection.snapshot()['nodes'] if result['metadata'].get('blockers')
                           else result['nodes'])
                for node in checked:
                    policy.resource(node.get('source_scope'))
                    if not node.get('sources') or any(not s.get('hash') for s in node['sources']):
                        raise DisclosureDenied()
                    for source in node['sources']:
                        policy.resource(source.get('source_scope'))
                    policy.evidence_metadata(self.grant_id(node), node)
                    label = node.get('policy_label', 'KnowledgeContext')
                    for field in node:
                        policy.property(label, field)
                    for prop in node.get('definition', {}).get('properties', {}):
                        policy.property(node.get('name', label), prop)
                    for rel in node.get('definition', {}).get('relationships', []):
                        for prop in rel.get('properties', []):
                            policy.property(rel['type'], prop['name'])
                return {'status': 'success', 'context': result}
        except Exception:
            # Match Stage 3: identical refusal for absent, malformed and denied.
            return dict(REFUSAL)
