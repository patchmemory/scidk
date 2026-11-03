"""Catalogue of the scientific tasks offered on the Review landing ("What scientific work are you trying to do?").

Pure data, no I/O: every card links to an existing workspace (``status='ready'``) and carries one fixed contextual Chat
prompt. Chat is a cross-cutting assistant surface, not a peer card: it is opened with ``chat_href`` which only pre-fills
the Chat input (``/review?view=guidance&prefill=...``; the Guidance URL is a compatibility name). Nothing is sent.
"""
from urllib.parse import quote

LEGACY_ASSERTIONS_PATH = '/review?view=assertions'
GUIDANCE_PATH = '/review?view=guidance'
CHAT_PATH = GUIDANCE_PATH
PREFILL_MAX = 1000


def chat_href(prompt=None):
    """App-relative URL that opens the Chat shell, optionally with ``prompt`` pre-filled (never submitted)."""
    text = (prompt or '').strip()[:PREFILL_MAX]
    return CHAT_PATH + ('&prefill=' + quote(text, safe='') if text else '')


def review_actions(assertions_enabled=False):
    """Return ``(actions, advanced)`` for the landing; paths are app-relative (the template adds the script root)."""
    def task(id, title, summary, primary, links, prompt):
        return dict(id=id, title=title, status='ready', summary=summary, primary=primary, links=links,
                    chat=dict(label='Discuss in Chat', prompt=prompt, href=chat_href(prompt)))
    actions = [
        task('curate', 'Curate',
             'Organize Collections and Datasets with their provenance and context.',
             dict(label='Open Collections', href='/datasets?view=collections'),
             [dict(label='Datasets', href='/datasets?view=datasets'),
              dict(label='Browse data', href='/datasets?view=browse')],
             'I am curating a collection of datasets. Help me think through how to group them and what provenance and context to keep.'),
        task('annotate', 'Annotate',
             'Add or review notes, descriptions, tags and corrections.',
             dict(label='Open Browse to annotate', href='/datasets?view=browse'),
             [],
             'I want to annotate my data. Help me decide which notes, descriptions, tags or corrections would be most useful.'),
        task('evaluate', 'Evaluate',
             'Check graph evidence, metadata completeness, run outcomes and inconsistencies.',
             dict(label='Open Relationships', href='/knowledge?view=relationships'),
             [dict(label='Entities', href='/knowledge?view=entities'),
              dict(label='Maps', href='/knowledge?view=maps'),
              dict(label='Runs', href='/resources?view=runs')],
             'I am evaluating my data. Help me look for gaps in metadata, weak evidence or inconsistencies between relationships and runs.'),
        task('enrich', 'Enrich',
             'Prepare sources, schema and mappings.',
             dict(label='Open Plugins & mapping', href='/resources?view=plugins'),
             [dict(label='Sources', href='/resources?view=sources')],
             'I want to enrich my data. Help me plan which sources, schema and mappings to prepare first.'),
        # Always a launcher: the Collections destination itself reports whether sharing-plan drafting is available.
        task('publish', 'Publish',
             'Prepare Collections and a sharing plan. Nothing is uploaded.',
             dict(label='Open Collections', href='/datasets?view=collections'),
             [],
             'I want to prepare a collection to share. Help me work out what metadata and context a sharing package needs.'),
    ]
    advanced = []
    if assertions_enabled:
        advanced.append(dict(label='Assertion review queue',
                             description='The existing evidence and assertion review workspace.',
                             href=LEGACY_ASSERTIONS_PATH))
    return actions, advanced
