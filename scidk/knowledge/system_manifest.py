"""Explicit small allowlist. Never recursively index code or configuration."""

def entry(id, type, path, **kwargs):
    return dict(id=id, type=type, path=path, **kwargs)


ENTRIES = [
    entry('workflow:scan', 'workflow', 'tools/SCIDK_SCANNER_SPEC.md', section='Purpose'),
    entry('workflow:csv-import', 'workflow', 'plugins/sharepoint_intake/README.md', section='Usage'),
    entry('workflow:intake-mapping', 'workflow', 'plugins/sharepoint_intake/README.md', section='Mapping (Pipeline, not plugin)'),
    entry('workflow:interpretation', 'workflow', 'docs/architecture/transparency-layers.md', section='Core Principle'),
    entry('workflow:commit', 'workflow', 'docs/architecture/transparency-layers.md', section='Design Principles'),
    entry('workflow:tool-discovery', 'workflow', 'scidk/agent_tools/registry.py'),
    entry('workflow:ontology', 'workflow', 'scidk/curation/ontology.py', symbol='Ontology'),
    entry('workflow:disclosure', 'workflow', 'docs/architecture/agent-disclosure-policy.md'),
    entry('doc:scanner', 'document', 'tools/SCIDK_SCANNER_SPEC.md'),
    entry('doc:intake', 'document', 'plugins/sharepoint_intake/README.md'),
    entry('doc:transparency', 'document', 'docs/architecture/transparency-layers.md'),
    entry('code:scanner', 'code_module', 'tools/scidk_scanner.py'),
    entry('code:scan-import', 'code_module', 'scidk/pipeline/passes/import_scan.py', symbol='import_scan'),
    entry('code:intake', 'code_module', 'plugins/sharepoint_intake/readers.py'),
    entry('code:mapping', 'code_module', 'scidk/pipeline/mapping_engine.py', symbol='MappingEngine'),
    entry('schema:mapping', 'schema', 'scidk/pipeline/mapping_schema.json'),
    entry('code:interpretation', 'code_module', 'scidk/core/analysis_context.py', symbol='AnalysisContext'),
    entry('code:commit', 'code_module', 'scidk/services/commit_service.py', symbol='CommitService'),
    entry('tool:registry', 'tool', 'scidk/agent_tools/registry.py', symbol='get_tool_definitions'),
    entry('code:ontology', 'code_module', 'scidk/curation/ontology.py', symbol='Ontology'),
    entry('schema:sample', 'schema', 'scidk/labels/builtin/sample.yaml'),
    entry('permission:disclosure', 'permission', 'docs/architecture/agent-disclosure-policy.md'),
    entry('code:disclosure', 'code_module', 'scidk/agent_tools/security.py', symbol='PolicyStore'),
]


def edge(source, type, target):
    return dict(source=source, type=type, target=target)


EDGES = [edge('workflow:' + name, 'REQUIRES', 'permission:disclosure') for name in
         ('scan', 'csv-import', 'intake-mapping', 'interpretation', 'commit', 'tool-discovery', 'ontology', 'disclosure')]
EDGES += [edge(*values) for values in [
    ('workflow:scan', 'DOCUMENTED_BY', 'doc:scanner'),
    ('workflow:scan', 'IMPLEMENTED_BY', 'code:scanner'),
    ('workflow:scan', 'IMPLEMENTED_BY', 'code:scan-import'),
    ('workflow:csv-import', 'DOCUMENTED_BY', 'doc:intake'),
    ('workflow:csv-import', 'IMPLEMENTED_BY', 'code:intake'),
    ('workflow:csv-import', 'REQUIRES', 'workflow:intake-mapping'),
    ('workflow:intake-mapping', 'IMPLEMENTED_BY', 'code:mapping'),
    ('workflow:intake-mapping', 'VALIDATED_BY', 'schema:mapping'),
    ('workflow:interpretation', 'DOCUMENTED_BY', 'doc:transparency'),
    ('workflow:interpretation', 'IMPLEMENTED_BY', 'code:interpretation'),
    ('workflow:commit', 'IMPLEMENTED_BY', 'code:commit'),
    ('workflow:commit', 'DOCUMENTED_BY', 'doc:transparency'),
    ('workflow:tool-discovery', 'EXPOSED_VIA', 'tool:registry'),
    ('workflow:ontology', 'IMPLEMENTED_BY', 'code:ontology'),
    ('workflow:ontology', 'DOCUMENTED_BY', 'schema:sample'),
    ('workflow:disclosure', 'IMPLEMENTED_BY', 'code:disclosure'),
    ('permission:disclosure', 'IMPLEMENTED_BY', 'code:disclosure'),
]]
