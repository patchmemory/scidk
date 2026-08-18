"""NIH DMS Plan generator plugin for SciDK.

Generates draft prose for four elements of an NIH Data Management and Sharing
plan out of whatever is actually in this instance's knowledge graph: entity
counts, file formats and volumes, measurement modalities, and — where the schema
layer defines them — per-property sharing modes.

The point of generating rather than templating is that the numbers are real. The
draft names the labels the graph holds, the formats the files are in and the
assays the records describe, so a researcher's first read is a review of their own
data rather than a fill-in-the-blanks exercise. Where a fact genuinely is not
available, the draft says so and asks for it; it never invents prose to fill a
gap, and it never falls back to a static plan when the graph is unreachable.

Entry point: ``GET /api/plugins/nih_dms/draft_plan`` → markdown.
"""

import logging

from . import config
from .generator import render_plan
from .graph_facts import GraphUnavailable, collect_facts

logger = logging.getLogger(__name__)

__all__ = [
    'collect_facts',
    'render_plan',
    'GraphUnavailable',
    'config',
    'register_plugin',
]

VERSION = '1.0.0'


def register_plugin(app):
    """Register the DMS plan generator's blueprint with SciDK.

    Args:
        app: Flask application instance.

    Returns:
        dict: Plugin metadata.
    """
    from .routes import bp

    # Plugins are discovered from disk on every startup, and a blueprint name may
    # only be registered once per app. Re-registering raises, which the loader
    # would record as a plugin failure — so an existing registration is treated as
    # success, which is what it is.
    if bp.name in app.blueprints:
        logger.debug('nih_dms: blueprint already registered')
    else:
        app.register_blueprint(bp)
        logger.info('NIH DMS plan generator registered at %s', bp.url_prefix)

    return {
        'name': 'NIH DMS Plan Generator',
        'version': VERSION,
        'author': 'SciDK Team',
        'description': (
            'Generates draft NIH Data Management and Sharing plan prose — data types, '
            'standards, preservation and access — from the live knowledge graph, and flags '
            'property names that look like direct identifiers.'
        ),
    }
