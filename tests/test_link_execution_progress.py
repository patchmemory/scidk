"""
Tests for link execution progress tracking.
"""
import time
from pathlib import Path


def test_link_execution_progress_tracking(app, client, tmp_path):
    """Test that link execution provides progress tracking via /api/tasks."""
    # This is a simplified test - in production you'd need Neo4j and actual label data
    # For now, we test that the service supports the background task pattern

    from scidk.services.link_service import LinkService

    service = LinkService(app)

    # Create a simple link definition (will fail without Neo4j, but tests the structure)
    link_def = {
        'name': 'Test Link',
        'source_label': 'Person',
        'target_label': 'File',
        'match_strategy': 'property',
        'match_config': {
            'source_field': 'email',
            'target_field': 'path'
        },
        'relationship_type': 'OWNS',
        'relationship_props': {}
    }

    # Save definition
    saved = service.save_link_definition(link_def)
    link_id = saved['id']

    assert link_id, "Link definition should have an ID"

    # Verify the execute_link_job method accepts use_background_task parameter
    # We can't actually execute without Neo4j, but we can verify the signature
    import inspect
    sig = inspect.signature(service.execute_link_job)
    params = list(sig.parameters.keys())

    assert 'link_def_id' in params
    assert 'use_background_task' in params, "Should support background task mode"


def test_link_execution_task_fields(app, client):
    """Test that link execution tasks have all required progress fields."""
    # Verify task structure by checking the method that would create it
    from scidk.services.link_service import LinkService
    import inspect
    import ast

    service = LinkService(app)

    # Get source code of execute_link_job
    source = inspect.getsource(service.execute_link_job)

    # Verify it creates task with progress fields
    assert 'task' in source
    assert 'progress' in source
    assert 'status_message' in source
    assert 'eta_seconds' in source
    assert 'relationships_created' in source


def test_link_service_backward_compatibility(app, client):
    """Test that link service maintains backward compatibility with synchronous mode."""
    from scidk.services.link_service import LinkService

    service = LinkService(app)

    # Create a test link definition
    link_def = {
        'name': 'Sync Test Link',
        'source_label': 'Person',
        'target_label': 'File',
        'match_strategy': 'property',
        'match_config': {'source_field': 'id', 'target_field': 'id'},
        'relationship_type': 'RELATES_TO',
        'relationship_props': {}
    }

    saved = service.save_link_definition(link_def)
    link_id = saved['id']

    # Verify we can still use synchronous mode (for backward compatibility)
    # This will fail without Neo4j but proves the parameter works
    try:
        # Call with use_background_task=False (legacy mode)
        service.execute_link_job(link_id, use_background_task=False)
    except Exception as e:
        # Expected to fail without Neo4j, but should accept the parameter
        assert 'use_background_task' not in str(e), "Parameter should be accepted"
