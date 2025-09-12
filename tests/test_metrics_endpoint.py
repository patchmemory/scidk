from scidk.app import create_app

def test_metrics_endpoint_exists():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        r = c.get('/api/metrics')
        assert r.status_code == 200
        data = r.get_json()
        # Expect keys present
        assert 'scan_throughput_per_min' in data
        assert 'rows_ingested_total' in data
        assert 'browse_latency_p50' in data
        assert 'browse_latency_p95' in data
        assert 'outbox_lag' in data
