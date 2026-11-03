"""Overview / Home content: three starting points and a restrained, honest workspace status.

No I/O beyond cheap, local, read-only checks (configuration lookup, one ``Path.exists``, an in-memory registry length).
Nothing here contacts the graph, a provider or the network; anything that cannot be determined is reported as Unknown.
"""
from pathlib import Path


def start_cards():
    return [
        dict(id='browse', title='Browse data',
             summary='Files, scans and recognized Datasets.',
             primary=dict(label='Open Datasets', href='/datasets?view=browse'),
             links=[dict(label='Collections', href='/datasets?view=collections')]),
        dict(id='explore', title='Explore knowledge',
             summary='Entities, Relationships, Maps and Sketch.',
             primary=dict(label='Open Relationships', href='/knowledge?view=relationships'),
             links=[dict(label='Entities', href='/knowledge?view=entities'),
                    dict(label='Maps', href='/knowledge?view=maps'),
                    dict(label='Sketch', href='/knowledge?view=sketch')]),
        dict(id='curate', title='Curate and review',
             summary='Organize context, assess metadata and evidence, and prepare material to share.',
             primary=dict(label='Open Review', href='/review'),
             links=[]),
    ]


def workspace_status(app):
    """List of ``dict(id, label, value, state)`` where state is ``ok`` / ``off`` / ``unknown``."""
    items = []
    try:
        from ..core.neo4j_config import get_neo4j_params
        uri, _user, _pwd, database, _mode = get_neo4j_params(app)
        configured = bool(uri and database)
        items.append(dict(id='graph', label='Graph',
                          value='Configured' if configured else 'Not configured', state='ok' if configured else 'off'))
    except Exception:
        items.append(dict(id='graph', label='Graph', value='Unknown', state='unknown'))
    try:
        db = app.config.get('SCIDK_DB_PATH')
        if not db:
            import os
            db = os.environ.get('SCIDK_DB_PATH')
        if not db:
            items.append(dict(id='inventory', label='Data inventory', value='Not configured', state='off'))
        else:
            exists = Path(db).exists()
            items.append(dict(id='inventory', label='Data inventory',
                              value='Available' if exists else 'Not configured', state='ok' if exists else 'off'))
    except Exception:
        items.append(dict(id='inventory', label='Data inventory', value='Unknown', state='unknown'))
    try:
        templates = (app.extensions.get('scidk') or {}).get('plugin_templates')
        count = len(templates.list_templates()) if templates is not None else None
        if count is None:
            items.append(dict(id='plugins', label='Sources and plugins', value='Unknown', state='unknown'))
        elif count:
            items.append(dict(id='plugins', label='Sources and plugins',
                              value='%d plugin template%s available' % (count, '' if count == 1 else 's'), state='ok'))
        else:
            items.append(dict(id='plugins', label='Sources and plugins', value='No plugin templates registered', state='off'))
    except Exception:
        items.append(dict(id='plugins', label='Sources and plugins', value='Unknown', state='unknown'))
    return items
