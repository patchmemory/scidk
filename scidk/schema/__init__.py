"""
scidk/schema/__init__.py

SciDK schema package. Provides type-safe access to all registered
Label node classes with tab-completion and inline sanitization docs.

Usage:
    from scidk.schema import Sample, ImagingDataset, Study

    # In an interpreter:
    dataset = ImagingDataset(
        path=str(file_path.parent),
        modality="microCT",
        voxel_size_um=5.0
    )
    result.node_created(dataset)

    # In a link script:
    from scidk.schema import Sample, Study
    # Sample.sample_id, Sample.species, etc. available with tab-complete

Generated stub classes live in scidk/schema/generated/.
Regenerate with: scidk labels generate-stubs

If generated stubs don't exist yet, this module falls back gracefully
and logs a warning. Run generate-stubs after adding Label definitions.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Try to import generated stubs
_generated_dir = os.path.join(os.path.dirname(__file__), 'generated')

if os.path.isdir(_generated_dir) and os.path.exists(os.path.join(_generated_dir, '__init__.py')):
    try:
        from scidk.schema.generated import *  # noqa: F401, F403
        from scidk.schema.generated import __all__
    except ImportError as e:
        logger.warning(
            f"Failed to import generated schema stubs: {e}. "
            f"Run 'scidk labels generate-stubs' to regenerate."
        )
        __all__ = []
else:
    logger.warning(
        "Schema stubs not generated yet. "
        "Run 'scidk labels generate-stubs' to generate type-safe Label classes."
    )
    __all__ = []

# Always export base class and core utilities
from scidk.schema.base import SciDKNode
from scidk.schema.registry import LabelRegistry
from scidk.schema.sanitization import apply_sanitization, sanitize_node_properties

__all__ = list(__all__) + ['SciDKNode', 'LabelRegistry', 'apply_sanitization', 'sanitize_node_properties']
