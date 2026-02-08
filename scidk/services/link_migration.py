"""
Migration utility for converting old link definitions to Label→Label model.

This module helps migrate existing link definitions from the old model:
- source_type: graph/csv/api
- target_type: graph/label

To the new Label→Label model:
- source_label: Label name (required)
- target_label: Label name (required)
- match_strategy: property/fuzzy/table_import/api_endpoint
"""
from __future__ import annotations
from typing import Dict, List, Any
import json


def migrate_link_definition(old_def: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate a single link definition from old to new format.

    Args:
        old_def: Old link definition dict

    Returns:
        Migrated link definition dict

    Raises:
        ValueError: If migration is not possible (missing required data)
    """
    migrated = old_def.copy()

    # Extract source label
    if 'source_label' not in migrated or not migrated['source_label']:
        source_type = old_def.get('source_type', '')
        source_config = old_def.get('source_config', {})

        if source_type == 'graph':
            # Extract label from graph source config
            source_label = source_config.get('label', '')
            if not source_label:
                raise ValueError(f"Cannot migrate link '{old_def.get('name')}': graph source missing label")
            migrated['source_label'] = source_label

        elif source_type == 'csv':
            # CSV becomes table_import match strategy
            # Need to infer or prompt for label name
            raise ValueError(
                f"Cannot auto-migrate CSV source for link '{old_def.get('name')}'. "
                f"Please manually specify source_label and update match_strategy to 'table_import'."
            )

        elif source_type == 'api':
            # API becomes api_endpoint match strategy
            raise ValueError(
                f"Cannot auto-migrate API source for link '{old_def.get('name')}'. "
                f"Please manually specify source_label and update match_strategy to 'api_endpoint'."
            )
        else:
            raise ValueError(f"Unknown source_type: {source_type}")

    # Extract target label
    if 'target_label' not in migrated or not migrated['target_label']:
        target_type = old_def.get('target_type', '')
        target_config = old_def.get('target_config', {})

        if target_type == 'label':
            target_label = target_config.get('label', '')
            if not target_label:
                raise ValueError(f"Cannot migrate link '{old_def.get('name')}': label target missing label name")
            migrated['target_label'] = target_label

        elif target_type == 'graph':
            target_label = target_config.get('label', '')
            if not target_label:
                raise ValueError(f"Cannot migrate link '{old_def.get('name')}': graph target missing label")
            migrated['target_label'] = target_label
        else:
            raise ValueError(f"Unknown target_type: {target_type}")

    # Update match strategy for CSV/API sources
    source_type = old_def.get('source_type', '')
    match_strategy = old_def.get('match_strategy', 'property')

    if source_type == 'csv' and match_strategy not in ['table_import', 'api_endpoint']:
        migrated['match_strategy'] = 'table_import'
        # Move CSV data to match_config if needed
        csv_data = old_def.get('source_config', {}).get('csv_data', '')
        if csv_data:
            migrated['match_config'] = migrated.get('match_config', {})
            migrated['match_config']['table_data'] = csv_data

    elif source_type == 'api' and match_strategy not in ['table_import', 'api_endpoint']:
        migrated['match_strategy'] = 'api_endpoint'
        # Move API config to match_config
        api_config = old_def.get('source_config', {})
        if api_config:
            migrated['match_config'] = migrated.get('match_config', {})
            migrated['match_config'].update(api_config)

    return migrated


def migrate_all_links(link_service) -> Dict[str, Any]:
    """
    Migrate all link definitions in the database.

    Args:
        link_service: LinkService instance

    Returns:
        Dict with migration results:
        {
            'migrated': [list of migrated link IDs],
            'skipped': [list of skipped link IDs with reasons],
            'errors': [list of error messages]
        }
    """
    results = {
        'migrated': [],
        'skipped': [],
        'errors': []
    }

    try:
        links = link_service.list_link_definitions()

        for link in links:
            link_id = link.get('id')
            link_name = link.get('name', 'Unknown')

            # Skip if already migrated
            if link.get('source_label') and link.get('target_label'):
                results['skipped'].append({
                    'id': link_id,
                    'name': link_name,
                    'reason': 'Already migrated'
                })
                continue

            try:
                migrated_link = migrate_link_definition(link)
                link_service.save_link_definition(migrated_link)
                results['migrated'].append({
                    'id': link_id,
                    'name': link_name
                })
            except ValueError as e:
                results['errors'].append({
                    'id': link_id,
                    'name': link_name,
                    'error': str(e)
                })
            except Exception as e:
                results['errors'].append({
                    'id': link_id,
                    'name': link_name,
                    'error': f"Unexpected error: {str(e)}"
                })

    except Exception as e:
        results['errors'].append({
            'error': f"Failed to list link definitions: {str(e)}"
        })

    return results


def generate_migration_report(results: Dict[str, Any]) -> str:
    """
    Generate a human-readable migration report.

    Args:
        results: Migration results from migrate_all_links()

    Returns:
        Formatted report string
    """
    report = []
    report.append("=== Link Migration Report ===\n")

    migrated = results.get('migrated', [])
    skipped = results.get('skipped', [])
    errors = results.get('errors', [])

    report.append(f"Migrated: {len(migrated)}")
    report.append(f"Skipped: {len(skipped)}")
    report.append(f"Errors: {len(errors)}\n")

    if migrated:
        report.append("Migrated Links:")
        for item in migrated:
            report.append(f"  ✓ {item['name']} ({item['id']})")
        report.append("")

    if skipped:
        report.append("Skipped Links:")
        for item in skipped:
            report.append(f"  - {item['name']}: {item['reason']}")
        report.append("")

    if errors:
        report.append("Errors:")
        for item in errors:
            if 'id' in item:
                report.append(f"  ✗ {item['name']} ({item['id']}): {item['error']}")
            else:
                report.append(f"  ✗ {item['error']}")
        report.append("")

    return "\n".join(report)
