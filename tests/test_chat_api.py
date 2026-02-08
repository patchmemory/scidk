import os
import pytest


def test_api_chat_echo(client):
    # First message
    resp1 = client.post('/api/chat', json={'message': 'Hello'})
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1['status'] == 'ok'
    assert data1['reply'].startswith('Echo:')
    assert len(data1['history']) == 2  # user + assistant

    # Second message should append
    resp2 = client.post('/api/chat', json={'message': 'How are you?'})
    data2 = resp2.get_json()
    assert len(data2['history']) == 4


def test_api_chat_missing_message(client):
    resp = client.post('/api/chat', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['status'] == 'error'
    assert 'message required' in data['error']


def test_api_chat_history(client):
    # Post a message first
    client.post('/api/chat', json={'message': 'Test'})

    # Get history
    resp = client.get('/api/chat/history')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert 'history' in data
    assert len(data['history']) >= 2


def test_api_chat_capabilities(client):
    resp = client.get('/api/chat/capabilities')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'graphrag' in data
    assert 'enabled' in data['graphrag']
    assert 'llm_provider' in data['graphrag']
    assert 'model' in data['graphrag']


def test_api_chat_graphrag_disabled_by_default(client):
    # GraphRAG should be disabled without SCIDK_GRAPHRAG_ENABLED
    resp = client.post('/api/chat/graphrag', json={'message': 'Test query'})
    assert resp.status_code == 501
    data = resp.get_json()
    assert data['status'] == 'disabled'
    assert 'SCIDK_GRAPHRAG_ENABLED' in data.get('hint', '')


def test_api_chat_graphrag_missing_message(client, monkeypatch):
    monkeypatch.setenv('SCIDK_GRAPHRAG_ENABLED', '1')
    resp = client.post('/api/chat/graphrag', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['status'] == 'error'
    assert 'message required' in data['error']


def test_api_chat_context_refresh_disabled(client):
    resp = client.post('/api/chat/context/refresh')
    assert resp.status_code == 501
    data = resp.get_json()
    assert data['status'] == 'disabled'


def test_api_chat_observability_graphrag(client):
    resp = client.get('/api/chat/observability/graphrag')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert 'enabled' in data
    assert 'llm_provider' in data
    assert 'model' in data
    assert 'schema' in data
    assert 'audit' in data
    assert isinstance(data['audit'], list)


# ========== Chat Session Persistence Tests ==========

def test_create_chat_session(client):
    """Test creating a new chat session."""
    resp = client.post('/api/chat/sessions', json={
        'name': 'Test Session',
        'metadata': {'tags': ['test'], 'test_session': True}
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert 'session' in data
    assert data['session']['name'] == 'Test Session'
    assert data['session']['message_count'] == 0
    assert data['session']['metadata']['tags'] == ['test']
    assert 'id' in data['session']
    assert 'created_at' in data['session']


def test_create_session_missing_name(client):
    """Test creating session without name fails."""
    resp = client.post('/api/chat/sessions', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'error' in data
    assert 'name' in data['error'].lower()


def test_list_chat_sessions(client):
    """Test listing all chat sessions."""
    # Create a few sessions
    client.post('/api/chat/sessions', json={'name': 'Session 1'})
    client.post('/api/chat/sessions', json={'name': 'Session 2'})

    # List sessions
    resp = client.get('/api/chat/sessions')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'sessions' in data
    assert len(data['sessions']) >= 2

    # Check ordering (most recent first)
    sessions = data['sessions']
    assert sessions[0]['name'] == 'Session 2'
    assert sessions[1]['name'] == 'Session 1'


def test_list_sessions_with_pagination(client):
    """Test pagination for session listing."""
    # Create several sessions
    for i in range(5):
        client.post('/api/chat/sessions', json={'name': f'Session {i}'})

    # Test limit
    resp = client.get('/api/chat/sessions?limit=2')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['sessions']) == 2

    # Test offset
    resp = client.get('/api/chat/sessions?limit=2&offset=2')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['sessions']) == 2


def test_get_chat_session(client):
    """Test getting a specific session with its messages."""
    # Create session
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test Session'})
    session_id = create_resp.get_json()['session']['id']

    # Add messages
    client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'user',
        'content': 'Hello'
    })
    client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'assistant',
        'content': 'Hi there!'
    })

    # Get session
    resp = client.get(f'/api/chat/sessions/{session_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['session']['id'] == session_id
    assert data['session']['message_count'] == 2
    assert len(data['messages']) == 2
    assert data['messages'][0]['role'] == 'user'
    assert data['messages'][0]['content'] == 'Hello'
    assert data['messages'][1]['role'] == 'assistant'
    assert data['messages'][1]['content'] == 'Hi there!'


def test_get_nonexistent_session(client):
    """Test getting a session that doesn't exist."""
    resp = client.get('/api/chat/sessions/nonexistent-uuid')
    assert resp.status_code == 404
    data = resp.get_json()
    assert 'error' in data


def test_update_chat_session(client):
    """Test updating session metadata."""
    # Create session
    create_resp = client.post('/api/chat/sessions', json={'name': 'Original Name'})
    session_id = create_resp.get_json()['session']['id']

    # Update name
    resp = client.put(f'/api/chat/sessions/{session_id}', json={
        'name': 'Updated Name'
    })
    assert resp.status_code == 200

    # Verify update
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    data = get_resp.get_json()
    assert data['session']['name'] == 'Updated Name'


def test_update_session_metadata(client):
    """Test updating session metadata."""
    # Create session
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test'})
    session_id = create_resp.get_json()['session']['id']

    # Update metadata
    resp = client.put(f'/api/chat/sessions/{session_id}', json={
        'metadata': {'tags': ['important'], 'color': 'blue'}
    })
    assert resp.status_code == 200

    # Verify update
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    data = get_resp.get_json()
    assert data['session']['metadata']['tags'] == ['important']
    assert data['session']['metadata']['color'] == 'blue'


def test_update_nonexistent_session(client):
    """Test updating a session that doesn't exist."""
    resp = client.put('/api/chat/sessions/nonexistent-uuid', json={'name': 'New Name'})
    assert resp.status_code == 404


def test_delete_chat_session(client):
    """Test deleting a session and its messages."""
    # Create session with messages
    create_resp = client.post('/api/chat/sessions', json={'name': 'To Delete'})
    session_id = create_resp.get_json()['session']['id']

    client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'user',
        'content': 'Test message'
    })

    # Delete session
    resp = client.delete(f'/api/chat/sessions/{session_id}')
    assert resp.status_code == 200

    # Verify deletion
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    assert get_resp.status_code == 404


def test_delete_nonexistent_session(client):
    """Test deleting a session that doesn't exist."""
    resp = client.delete('/api/chat/sessions/nonexistent-uuid')
    assert resp.status_code == 404


def test_add_message_to_session(client):
    """Test adding messages to a session."""
    # Create session
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test'})
    session_id = create_resp.get_json()['session']['id']

    # Add user message
    resp = client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'user',
        'content': 'What is 2+2?',
        'metadata': {'context': 'math'}
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['message']['role'] == 'user'
    assert data['message']['content'] == 'What is 2+2?'
    assert data['message']['metadata']['context'] == 'math'
    assert 'timestamp' in data['message']

    # Add assistant message
    resp = client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'assistant',
        'content': '2+2 equals 4'
    })
    assert resp.status_code == 201

    # Verify session message count updated
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    data = get_resp.get_json()
    assert data['session']['message_count'] == 2


def test_add_message_invalid_role(client):
    """Test adding message with invalid role."""
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test'})
    session_id = create_resp.get_json()['session']['id']

    resp = client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'invalid',
        'content': 'Test'
    })
    assert resp.status_code == 400


def test_add_message_missing_content(client):
    """Test adding message without content."""
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test'})
    session_id = create_resp.get_json()['session']['id']

    resp = client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'user'
    })
    assert resp.status_code == 400


def test_add_message_to_nonexistent_session(client):
    """Test adding message to non-existent session."""
    resp = client.post('/api/chat/sessions/nonexistent/messages', json={
        'role': 'user',
        'content': 'Test'
    })
    assert resp.status_code == 404


def test_export_chat_session(client):
    """Test exporting a session as JSON."""
    # Create session with messages
    create_resp = client.post('/api/chat/sessions', json={
        'name': 'Export Test',
        'metadata': {'tags': ['export']}
    })
    session_id = create_resp.get_json()['session']['id']

    client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'user',
        'content': 'Question'
    })
    client.post(f'/api/chat/sessions/{session_id}/messages', json={
        'role': 'assistant',
        'content': 'Answer'
    })

    # Export session
    resp = client.get(f'/api/chat/sessions/{session_id}/export')
    assert resp.status_code == 200
    data = resp.get_json()

    # Verify export structure
    assert 'session' in data
    assert 'messages' in data
    assert data['session']['name'] == 'Export Test'
    assert data['session']['metadata']['tags'] == ['export']
    assert len(data['messages']) == 2
    assert data['messages'][0]['role'] == 'user'
    assert data['messages'][1]['role'] == 'assistant'


def test_export_nonexistent_session(client):
    """Test exporting a session that doesn't exist."""
    resp = client.get('/api/chat/sessions/nonexistent/export')
    assert resp.status_code == 404


def test_import_chat_session(client):
    """Test importing a session from JSON."""
    # Prepare import data
    import_data = {
        'session': {
            'id': 'old-uuid',
            'name': 'Imported Session',
            'metadata': {'imported': True},
            'created_at': 1234567890.0,
            'updated_at': 1234567890.0,
            'message_count': 2
        },
        'messages': [
            {
                'id': 'msg1',
                'session_id': 'old-uuid',
                'role': 'user',
                'content': 'Imported question',
                'timestamp': 1234567890.0,
                'metadata': {}
            },
            {
                'id': 'msg2',
                'session_id': 'old-uuid',
                'role': 'assistant',
                'content': 'Imported answer',
                'timestamp': 1234567891.0,
                'metadata': {}
            }
        ]
    }

    # Import session
    resp = client.post('/api/chat/sessions/import', json={
        'data': import_data
    })
    assert resp.status_code == 201
    data = resp.get_json()

    # Verify import (should have new UUID)
    assert data['session']['name'] == 'Imported Session'
    assert data['session']['id'] != 'old-uuid'  # New UUID assigned
    assert data['session']['message_count'] == 2

    # Verify messages were imported
    session_id = data['session']['id']
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    get_data = get_resp.get_json()
    assert len(get_data['messages']) == 2
    assert get_data['messages'][0]['content'] == 'Imported question'
    assert get_data['messages'][1]['content'] == 'Imported answer'


def test_import_session_with_new_name(client):
    """Test importing a session with a custom name."""
    import_data = {
        'session': {
            'id': 'old-uuid',
            'name': 'Original Name',
            'metadata': {},
            'created_at': 1234567890.0,
            'updated_at': 1234567890.0,
            'message_count': 0
        },
        'messages': []
    }

    resp = client.post('/api/chat/sessions/import', json={
        'data': import_data,
        'new_name': 'Custom Import Name'
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['session']['name'] == 'Custom Import Name'


def test_import_invalid_data(client):
    """Test importing with invalid data."""
    resp = client.post('/api/chat/sessions/import', json={
        'data': {'invalid': 'structure'}
    })
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'error' in data


def test_session_cascade_delete(client):
    """Test that deleting a session cascades to messages."""
    # Create session with multiple messages
    create_resp = client.post('/api/chat/sessions', json={'name': 'Cascade Test', 'metadata': {'test_session': True}})
    session_id = create_resp.get_json()['session']['id']

    # Add several messages
    for i in range(5):
        client.post(f'/api/chat/sessions/{session_id}/messages', json={
            'role': 'user' if i % 2 == 0 else 'assistant',
            'content': f'Message {i}'
        })

    # Verify messages exist
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    assert len(get_resp.get_json()['messages']) == 5

    # Delete session
    client.delete(f'/api/chat/sessions/{session_id}')

    # Verify session and messages are gone
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    assert get_resp.status_code == 404


def test_cleanup_test_sessions(client):
    """Test bulk cleanup of test sessions."""
    import uuid
    test_run_id = str(uuid.uuid4())

    # Create mix of test sessions with different test_ids
    client.post('/api/chat/sessions', json={
        'name': 'Test Run 1',
        'metadata': {'test_session': True, 'test_id': test_run_id}
    })
    client.post('/api/chat/sessions', json={
        'name': 'Test Run 2',
        'metadata': {'test_session': True, 'test_id': test_run_id}
    })
    client.post('/api/chat/sessions', json={
        'name': 'Other Test',
        'metadata': {'test_session': True, 'test_id': 'other-id'}
    })
    client.post('/api/chat/sessions', json={
        'name': 'Real Session',
        'metadata': {'user_created': True}
    })

    # Cleanup specific test run
    resp = client.delete(f'/api/chat/sessions/test-cleanup?test_id={test_run_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted_count'] == 2

    # Verify correct sessions deleted
    sessions_resp = client.get('/api/chat/sessions')
    sessions = sessions_resp.get_json()['sessions']
    session_names = [s['name'] for s in sessions]
    assert 'Test Run 1' not in session_names
    assert 'Test Run 2' not in session_names
    assert 'Other Test' in session_names  # Different test_id
    assert 'Real Session' in session_names  # Not a test session


def test_cleanup_all_test_sessions(client):
    """Test cleanup of all test sessions."""
    # Create test and real sessions
    client.post('/api/chat/sessions', json={
        'name': 'Test A',
        'metadata': {'test_session': True}
    })
    client.post('/api/chat/sessions', json={
        'name': 'Test B',
        'metadata': {'test_session': True}
    })
    client.post('/api/chat/sessions', json={
        'name': 'Real User Session',
        'metadata': {}
    })

    # Cleanup all test sessions
    resp = client.delete('/api/chat/sessions/test-cleanup')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted_count'] >= 2  # At least our 2 test sessions

    # Verify real session still exists
    sessions_resp = client.get('/api/chat/sessions')
    sessions = sessions_resp.get_json()['sessions']
    session_names = [s['name'] for s in sessions]
    assert 'Real User Session' in session_names


# ========== Permissions & Sharing Tests ==========

def test_session_default_visibility(client):
    """Test that sessions default to private visibility."""
    resp = client.post('/api/chat/sessions', json={'name': 'Test Session', 'metadata': {'test_session': True}})
    assert resp.status_code == 201

    session_id = resp.get_json()['session']['id']

    # Get session and check default visibility
    get_resp = client.get(f'/api/chat/sessions/{session_id}')
    data = get_resp.get_json()

    # Should default to private with system owner
    session = data['session']
    assert session.get('visibility', 'private') == 'private'
    assert session.get('owner', 'system') == 'system'


def test_set_visibility_invalid(client):
    """Test setting invalid visibility fails (without auth, expecting 401)."""
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test', 'metadata': {'test_session': True}})
    session_id = create_resp.get_json()['session']['id']

    resp = client.put(f'/api/chat/sessions/{session_id}/visibility', json={
        'visibility': 'invalid_value'
    })

    # Without auth, should get 401, or 400 if validation happens first
    assert resp.status_code in (400, 401)


def test_list_permissions_requires_admin(client):
    """Test that listing permissions requires admin access."""
    # Create session
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test', 'metadata': {'test_session': True}})
    session_id = create_resp.get_json()['session']['id']

    # Try to list permissions without auth
    resp = client.get(f'/api/chat/sessions/{session_id}/permissions')

    # Should require authentication
    assert resp.status_code == 401


def test_grant_permission_invalid_level(client):
    """Test granting invalid permission level fails."""
    create_resp = client.post('/api/chat/sessions', json={'name': 'Test', 'metadata': {'test_session': True}})
    session_id = create_resp.get_json()['session']['id']

    resp = client.post(f'/api/chat/sessions/{session_id}/permissions', json={
        'username': 'alice',
        'permission': 'superuser'  # Invalid
    })

    # Without auth should be 401, or 400 if validation happens first
    assert resp.status_code in (400, 401)


def test_permission_hierarchy(client, tmp_path):
    """Test that permission levels work hierarchically (admin > edit > view)."""
    # This tests the service layer logic
    from scidk.services.chat_service import get_chat_service

    # Use a temporary file database instead of :memory:
    db_path = str(tmp_path / "test.db")
    chat_service = get_chat_service(db_path=db_path)

    # Create a test session
    session = chat_service.create_session('Test Session')
    session_id = session.id

    # Set owner for grant to work
    conn = chat_service._get_conn()
    try:
        conn.execute("UPDATE chat_sessions SET owner = ? WHERE id = ?", ('admin', session_id))
        conn.commit()
    finally:
        conn.close()

    # Grant edit permission to alice
    chat_service.grant_permission(session_id, 'alice', 'edit', 'admin')

    # Alice should have view access (edit includes view)
    assert chat_service.check_permission(session_id, 'alice', 'view') is True

    # Alice should have edit access
    assert chat_service.check_permission(session_id, 'alice', 'edit') is True

    # Alice should NOT have admin access
    assert chat_service.check_permission(session_id, 'alice', 'admin') is False


def test_owner_has_full_access(client, tmp_path):
    """Test that session owner has automatic full access."""
    from scidk.services.chat_service import get_chat_service

    db_path = str(tmp_path / "test_owner.db")
    chat_service = get_chat_service(db_path=db_path)

    # Create session with specific owner
    session = chat_service.create_session('Owner Test')
    session_id = session.id

    # Manually set owner
    conn = chat_service._get_conn()
    try:
        conn.execute("UPDATE chat_sessions SET owner = ? WHERE id = ?", ('bob', session_id))
        conn.commit()
    finally:
        conn.close()

    # Owner should have all permissions without explicit grant
    assert chat_service.check_permission(session_id, 'bob', 'view') is True
    assert chat_service.check_permission(session_id, 'bob', 'edit') is True
    assert chat_service.check_permission(session_id, 'bob', 'admin') is True


def test_public_visibility_allows_view(client, tmp_path):
    """Test that public sessions allow view access to everyone."""
    from scidk.services.chat_service import get_chat_service

    db_path = str(tmp_path / "test_public.db")
    chat_service = get_chat_service(db_path=db_path)

    # Create and make public
    session = chat_service.create_session('Public Session')
    session_id = session.id

    # Set visibility to public
    conn = chat_service._get_conn()
    try:
        conn.execute("UPDATE chat_sessions SET visibility = ?, owner = ? WHERE id = ?", ('public', 'owner', session_id))
        conn.commit()
    finally:
        conn.close()

    # Anyone should be able to view
    assert chat_service.check_permission(session_id, 'random_user', 'view') is True

    # But not edit or admin
    assert chat_service.check_permission(session_id, 'random_user', 'edit') is False
    assert chat_service.check_permission(session_id, 'random_user', 'admin') is False


def test_cascade_delete_permissions(client, tmp_path):
    """Test that deleting session also deletes permissions."""
    from scidk.services.chat_service import get_chat_service

    db_path = str(tmp_path / "test_cascade.db")
    chat_service = get_chat_service(db_path=db_path)

    # Create session and grant permissions
    session = chat_service.create_session('Test')
    session_id = session.id

    # Set owner and grant permissions
    conn = chat_service._get_conn()
    try:
        conn.execute("UPDATE chat_sessions SET owner = ? WHERE id = ?", ('admin', session_id))
        conn.commit()
    finally:
        conn.close()

    chat_service.grant_permission(session_id, 'alice', 'view', 'admin')
    chat_service.grant_permission(session_id, 'bob', 'edit', 'admin')

    # Verify permissions exist
    permissions = chat_service.list_permissions(session_id, 'admin')
    assert len(permissions) == 2

    # Delete session
    chat_service.delete_session(session_id)

    # Permissions should be gone (cascade delete)
    # Try to get permissions - should return None (session doesn't exist)
    result = chat_service.list_permissions(session_id, 'admin')
    assert result is None
