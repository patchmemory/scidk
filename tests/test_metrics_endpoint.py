from scidk.app import create_app
from tests.conftest import authenticate_test_client

def test_metrics_endpoint_exists():
    app = create_app()
    app.config['TESTING'] = True
    with authenticate_test_client(app.test_client(), app) as c:
        r = c.get('/api/metrics')
        assert r.status_code == 200
        data = r.get_json()
        # Expect keys present
        assert 'scan_throughput_per_min' in data
        assert 'rows_ingested_total' in data
        assert 'browse_latency_p50' in data
        assert 'browse_latency_p95' in data
        assert 'outbox_lag' in data
