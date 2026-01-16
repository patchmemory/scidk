import time
from scidk.app import create_app


def test_logs_endpoint_exists():
    """Test that /api/logs endpoint exists and returns expected structure."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = c.get('/api/logs')
        assert r.status_code == 200
        data = r.get_json()
        # Expect keys present
        assert 'logs' in data
        assert 'total' in data
        assert 'limit' in data
        assert 'offset' in data
        assert isinstance(data['logs'], list)


def test_logs_endpoint_pagination():
    """Test that pagination parameters work correctly."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        # Test with custom limit and offset
        r = c.get('/api/logs?limit=5&offset=0')
        assert r.status_code == 200
        data = r.get_json()
        assert data['limit'] == 5
        assert data['offset'] == 0
        assert len(data['logs']) <= 5


def test_logs_endpoint_level_filter():
    """Test that level filter works correctly."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        # Insert a test log entry
        from scidk.core import path_index_sqlite as pix
        conn = pix.connect()
        try:
            from scidk.core import migrations as _migs
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO logs (ts, level, message, context) VALUES (?, ?, ?, ?)",
                (time.time(), 'ERROR', 'Test error message', None)
            )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        # Query with level filter
        r = c.get('/api/logs?level=ERROR')
        assert r.status_code == 200
        data = r.get_json()
        # Should have at least our test error
        error_logs = [log for log in data['logs'] if log['level'] == 'ERROR']
        assert len(error_logs) > 0


def test_logs_endpoint_since_ts_filter():
    """Test that since_ts filter works correctly."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        # Insert test log entries with different timestamps
        from scidk.core import path_index_sqlite as pix
        conn = pix.connect()
        try:
            from scidk.core import migrations as _migs
            _migs.migrate(conn)
            cur = conn.cursor()
            now = time.time()
            cur.execute(
                "INSERT INTO logs (ts, level, message, context) VALUES (?, ?, ?, ?)",
                (now - 100, 'INFO', 'Old log', None)
            )
            cur.execute(
                "INSERT INTO logs (ts, level, message, context) VALUES (?, ?, ?, ?)",
                (now, 'INFO', 'Recent log', None)
            )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        # Query with since_ts filter (only recent logs)
        cutoff = time.time() - 50
        r = c.get(f'/api/logs?since_ts={cutoff}')
        assert r.status_code == 200
        data = r.get_json()
        # All returned logs should be after cutoff
        for log in data['logs']:
            assert log['ts'] >= cutoff


def test_logs_endpoint_no_sensitive_data():
    """Test that logs don't expose sensitive file paths or user data."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = c.get('/api/logs')
        assert r.status_code == 200
        data = r.get_json()
        # Verify response structure contains only safe fields
        for log in data['logs']:
            assert set(log.keys()) == {'ts', 'level', 'message', 'context'}
            # No 'user', 'password', 'secret', etc. fields
            assert 'user' not in log
            assert 'password' not in log
            assert 'secret' not in log
