"""
scidk/schema/sanitization.py

The sanitization pipeline — runs between property declaration and Neo4j write.

This module is called by SciDKNode.to_cypher_props() and by
neo4j_client.write_declared_nodes() before any Cypher execution.

It is the enforcement layer for Label-defined sanitization policies.
No module can bypass it — sanitization runs at the write layer,
not inside individual scripts.

Sanitization rules (defined in Label YAML):

    none      — pass through unchanged
    redact    — drop property entirely, never written
    hash      — one-way SHA-256, preserves linkability
    bin       — numeric binning to range string e.g. 45 → "40-50 years"
    encode    — map to controlled vocabulary term
    truncate  — round to reduce numeric precision

If a rule fails (bad config, unexpected value type), the property is
passed through unchanged and a warning is emitted. Failed sanitization
never prevents a write — it logs and continues.
"""

from __future__ import annotations
import hashlib
import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def apply_sanitization(
    properties: Dict[str, Any],
    sanitization_rules: Dict[str, Dict],
) -> Dict[str, Any]:
    """
    Apply sanitization rules to a properties dict.

    Args:
        properties: Raw property dict from SciDKNode.to_raw_props()
        sanitization_rules: Dict mapping property name to rule config.
            Format: {'donor_age': {'rule': 'bin', 'bin_size': 10, 'units': 'years'}}

    Returns:
        Sanitized properties dict. Redacted properties are absent.
        Unknown properties (no rule defined) pass through unchanged.

    Never raises. Logs warnings for rule failures.
    """
    if not sanitization_rules:
        return properties

    sanitized = {}

    for prop_name, value in properties.items():
        rule_config = sanitization_rules.get(prop_name)

        if rule_config is None:
            # No rule for this property — pass through
            sanitized[prop_name] = value
            continue

        rule = rule_config.get('rule', 'none')

        try:
            result = _apply_rule(prop_name, value, rule, rule_config)
            if result is not _REDACTED:
                sanitized[prop_name] = result
        except Exception as e:
            logger.warning(
                f"Sanitization rule '{rule}' failed for property '{prop_name}': {e}. "
                f"Passing through unchanged."
            )
            sanitized[prop_name] = value

    return sanitized


# Sentinel for redacted values
class _RedactedSentinel:
    def __repr__(self):
        return "<REDACTED>"

_REDACTED = _RedactedSentinel()


def _apply_rule(
    prop_name: str,
    value: Any,
    rule: str,
    config: Dict,
) -> Any:
    """Apply a single sanitization rule. Returns _REDACTED sentinel for redact rule."""

    if rule == 'none':
        return value

    elif rule == 'redact':
        return _REDACTED

    elif rule == 'hash':
        return _hash_value(value, config)

    elif rule == 'bin':
        return _bin_value(value, config)

    elif rule == 'encode':
        return _encode_value(prop_name, value, config)

    elif rule == 'truncate':
        return _truncate_value(value, config)

    else:
        logger.warning(f"Unknown sanitization rule '{rule}' for '{prop_name}'. Passing through.")
        return value


# ─── Rule implementations ─────────────────────────────────────────────────────

def _hash_value(value: Any, config: Dict) -> str:
    """
    One-way SHA-256 hash. Deterministic — same input always produces same output.

    Config options:
        preserve_linkability (bool, default True): use consistent hashing
        salt (str, default ""): prepend salt before hashing
            WARNING: salting breaks cross-dataset linkability
        prefix (str, default "hash:"): prefix on stored value for readability
    """
    salt = config.get('salt', '')
    prefix = config.get('prefix', 'hash:')
    input_str = f"{salt}{str(value)}"
    hashed = hashlib.sha256(input_str.encode('utf-8')).hexdigest()[:16]
    return f"{prefix}{hashed}"


def _bin_value(value: Any, config: Dict) -> str:
    """
    Bin a numeric value into a range string.

    Config options:
        bin_size (int/float, required): width of each bin
        units (str, default ""): appended to range string
        format (str, default "{low}-{high}"): range string template

    Example:
        value=45, bin_size=10, units="years" → "40-50 years"
        value=73, bin_size=5               → "70-75"
    """
    bin_size = config.get('bin_size')
    if bin_size is None:
        raise ValueError("bin rule requires sanitize_config.bin_size")

    units = config.get('units', '')
    fmt = config.get('format', '{low}-{high}')

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Cannot bin non-numeric value: {value!r}")

    low = int(math.floor(numeric / bin_size) * bin_size)
    high = low + int(bin_size)

    range_str = fmt.format(low=low, high=high)
    if units:
        range_str = f"{range_str} {units}"

    return range_str


def _encode_value(prop_name: str, value: Any, config: Dict) -> Any:
    """
    Map value to a controlled vocabulary term.

    Config options:
        vocabulary (str, required): vocabulary name registered in SciDK
        fallback (str, default "hash"): rule to apply if term not found
            "hash" | "redact" | "none"
        case_sensitive (bool, default False)

    The vocabulary registry is loaded from scidk/vocabularies/.
    If the vocabulary is not registered, falls back without error.
    """
    vocab_name = config.get('vocabulary')
    fallback = config.get('fallback', 'hash')
    case_sensitive = config.get('case_sensitive', False)

    if not vocab_name:
        raise ValueError("encode rule requires sanitize_config.vocabulary")

    # Load vocabulary — returns None if not registered (graceful degradation)
    vocabulary = _load_vocabulary(vocab_name)

    if vocabulary is None:
        logger.warning(
            f"Vocabulary '{vocab_name}' not registered for property '{prop_name}'. "
            f"Applying fallback '{fallback}'."
        )
        return _apply_rule(prop_name, value, fallback, {})

    str_value = str(value)
    lookup_value = str_value if case_sensitive else str_value.lower()

    for term, variants in vocabulary.items():
        lookup_variants = variants if case_sensitive else [v.lower() for v in variants]
        if lookup_value in lookup_variants or lookup_value == (term.lower() if not case_sensitive else term):
            return term  # Return canonical term

    # Not found in vocabulary — apply fallback
    logger.debug(
        f"Value '{value}' not found in vocabulary '{vocab_name}' for '{prop_name}'. "
        f"Applying fallback '{fallback}'."
    )
    return _apply_rule(prop_name, value, fallback, config)


def _truncate_value(value: Any, config: Dict) -> Any:
    """
    Round a numeric value to reduce precision.

    Config options:
        decimal_places (int, default 0): number of decimal places to keep
    """
    decimal_places = config.get('decimal_places', 0)

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Cannot truncate non-numeric value: {value!r}")

    rounded = round(numeric, decimal_places)

    # Return int if decimal_places is 0
    if decimal_places == 0:
        return int(rounded)
    return rounded


def _load_vocabulary(vocab_name: str) -> Optional[Dict[str, list]]:
    """
    Load a controlled vocabulary from the SciDK vocabulary registry.

    Vocabularies are YAML files in scidk/vocabularies/{vocab_name}.yaml.
    Format:
        canonical_term:
          - variant1
          - variant2

    Returns None if vocabulary not found (graceful degradation).
    """
    import os
    import yaml

    vocab_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'vocabularies'
    )
    vocab_path = os.path.join(vocab_dir, f"{vocab_name.lower().replace('-', '_')}.yaml")

    if not os.path.exists(vocab_path):
        return None

    try:
        with open(vocab_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Failed to load vocabulary '{vocab_name}': {e}")
        return None


# ─── Convenience functions for neo4j_client.py ───────────────────────────────

def sanitize_node_properties(
    label_name: str,
    properties: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Convenience function for neo4j_client.write_declared_nodes().
    Loads sanitization rules from the Label registry and applies them.

    If the label is not registered, properties pass through unchanged.
    This ensures unknown labels from older interpreters still write successfully.
    """
    from scidk.schema.registry import LabelRegistry

    label_def = LabelRegistry.get(label_name)
    if label_def is None:
        return properties

    return apply_sanitization(properties, label_def.sanitization_rules)
