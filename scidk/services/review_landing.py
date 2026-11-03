"""Catalogue of the actions offered on the Review landing ("What would you like to do with your science data?").

Pure data, no I/O: every card either links to an existing workspace (``status='ready'``) or is an honest
placeholder (``status='future'`` / ``'unavailable'``) that renders no link. Later work (harmonization, enrichment,
publication/SciDO preparation, AI-assisted reasoning, operational guidance) adds an entry to ``review_actions`` and
nothing else; the template renders whatever the catalogue returns.
"""

LEGACY_ASSERTIONS_PATH = '/review?view=assertions'
GUIDANCE_PATH = '/review?view=guidance'


def review_actions(assertions_enabled=False):
    """Return ``(actions, advanced)`` for the landing; paths are app-relative (the template adds the script root)."""
    actions = [
        dict(id='understand', title='Understand data', status='ready',
             summary='See how entities relate. Inspect relationships, entities, maps and the contextual graph structure around them.',
             primary=dict(label='Open Relationships', href='/knowledge?view=relationships'),
             links=[dict(label='Entities', href='/knowledge?view=entities'),
                    dict(label='Maps', href='/knowledge?view=maps')]),
        dict(id='organize', title='Organize context', status='ready',
             summary='Group related material for a scientific purpose with Collections and Datasets.',
             primary=dict(label='Open Collections', href='/datasets?view=collections'),
             links=[dict(label='Datasets', href='/datasets?view=datasets')]),
        dict(id='metadata', title='Improve metadata', status='ready',
             summary='Prepare sources and reach the schema and column-mapping tools. Enrichment will build on these.',
             primary=dict(label='Open Plugins & mapping', href='/resources?view=plugins'),
             links=[dict(label='Sources', href='/resources?view=sources')]),
        dict(id='explore', title='Explore', status='ready',
             summary='Browse data locations and datasets, or look at graph views and saved maps.',
             primary=dict(label='Browse data', href='/datasets?view=browse'),
             links=[dict(label='Saved maps', href='/knowledge?view=maps')]),
        # Always a launcher: the Collections destination itself reports whether sharing-plan drafting is available.
        dict(id='share', title='Prepare to share', status='ready',
             summary='Open a saved Collection to draft a dataset sharing plan and preview a data-management-sharing package. Nothing is uploaded.',
             primary=dict(label='Open Collections', href='/datasets?view=collections'), links=[]),
    ]
    # Chat (formerly Guidance; ids and URLs keep the old name) is a launcher to the chat-style shell (/review?view=guidance). The shell makes no provider or network
    # call and fabricates nothing; it states plainly that no AI provider is configured until one is wired in.
    actions.append(dict(id='guidance', title='Chat', status='ready',
             summary='Ask questions about your data and next steps in a chat-style workspace. The AI provider is not configured yet, so this opens the chat surface without any answers.',
             primary=dict(label='Open Chat', href=GUIDANCE_PATH), links=[]))
    advanced = []
    if assertions_enabled:
        advanced.append(dict(label='Assertion review queue',
                             description='The existing evidence and assertion review workspace.',
                             href=LEGACY_ASSERTIONS_PATH))
    return actions, advanced
