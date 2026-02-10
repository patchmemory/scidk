"""
Tests for comprehensive health dashboard API endpoint.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture()
def admin_client(client):
    """Provide an authenticated admin client (alias for existing client fixture).

    The client fixture already handles admin authentication when auth is enabled,
    so we just use it directly.
    """
    return client


def test_health_comprehensive_endpoint_exists(client):
    """Test that the comprehensive health endpoint returns 200."""
    resp = client.get('/api/health/comprehensive')
    # Endpoint is public (no auth required)
    assert resp.status_code == 200


def test_health_comprehensive_structure(admin_client):
    """Test that comprehensive health endpoint returns expected structure."""
    resp = admin_client.get('/api/health/comprehensive')

    # Should succeed for admin
    assert resp.status_code == 200

    data = resp.get_json()

    # Top-level fields
    assert 'status' in data
    assert 'timestamp' in data
    assert 'components' in data

    # Status should be one of the expected values
    assert data['status'] in ['healthy', 'warning', 'critical']

    # Timestamp should be a number
    assert isinstance(data['timestamp'], (int, float))

    # Components should be a dict
    assert isinstance(data['components'], dict)


def test_health_comprehensive_components(admin_client):
    """Test that all expected components are present in health response."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    components = data['components']

    # Expected components
    expected = ['flask', 'sqlite', 'neo4j', 'interpreters', 'disk', 'memory', 'cpu']

    for component in expected:
        assert component in components, f"Missing component: {component}"
        assert 'status' in components[component], f"Component {component} missing status"


def test_health_flask_component(admin_client):
    """Test Flask component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    flask = data['components']['flask']

    assert 'status' in flask
    if flask['status'] == 'ok':
        assert 'uptime_seconds' in flask
        assert 'memory_mb' in flask
        assert isinstance(flask['uptime_seconds'], int)
        assert isinstance(flask['memory_mb'], (int, float))
    elif flask['status'] == 'error':
        assert 'error' in flask


def test_health_sqlite_component(admin_client):
    """Test SQLite component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    sqlite = data['components']['sqlite']

    assert 'status' in sqlite
    if sqlite['status'] == 'ok':
        assert 'path' in sqlite
        assert 'size_mb' in sqlite
        assert 'journal_mode' in sqlite
        assert 'row_count' in sqlite
        assert isinstance(sqlite['size_mb'], (int, float))
        assert isinstance(sqlite['row_count'], int)
    elif sqlite['status'] == 'error':
        assert 'error' in sqlite


def test_health_neo4j_component(admin_client):
    """Test Neo4j component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    neo4j = data['components']['neo4j']

    assert 'status' in neo4j
    # Neo4j can be: connected, unavailable, not_configured, or error
    assert neo4j['status'] in ['connected', 'unavailable', 'not_configured', 'error']

    if neo4j['status'] == 'connected':
        assert 'response_time_ms' in neo4j
        assert 'node_count' in neo4j
    elif neo4j['status'] in ['unavailable', 'error']:
        assert 'error' in neo4j or neo4j['status'] == 'unavailable'


def test_health_interpreters_component(admin_client):
    """Test interpreters component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    interpreters = data['components']['interpreters']

    assert 'status' in interpreters
    if interpreters['status'] == 'ok':
        assert 'enabled_count' in interpreters
        assert 'total_count' in interpreters
        assert isinstance(interpreters['enabled_count'], int)
        assert isinstance(interpreters['total_count'], int)
        assert interpreters['enabled_count'] <= interpreters['total_count']
    elif interpreters['status'] == 'error':
        assert 'error' in interpreters


def test_health_disk_component(admin_client):
    """Test disk component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    disk = data['components']['disk']

    assert 'status' in disk
    if disk['status'] in ['good', 'warning', 'critical']:
        assert 'free_gb' in disk
        assert 'total_gb' in disk
        assert 'percent_used' in disk
        assert isinstance(disk['free_gb'], (int, float))
        assert isinstance(disk['total_gb'], (int, float))
        assert isinstance(disk['percent_used'], (int, float))
        assert 0 <= disk['percent_used'] <= 100
    elif disk['status'] == 'error':
        assert 'error' in disk


def test_health_memory_component(admin_client):
    """Test memory component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    memory = data['components']['memory']

    assert 'status' in memory
    if memory['status'] in ['normal', 'high', 'critical']:
        assert 'used_mb' in memory
        assert 'total_mb' in memory
        assert 'percent_used' in memory
        assert isinstance(memory['used_mb'], (int, float))
        assert isinstance(memory['total_mb'], (int, float))
        assert isinstance(memory['percent_used'], (int, float))
        assert 0 <= memory['percent_used'] <= 100
    elif memory['status'] == 'error':
        assert 'error' in memory


def test_health_cpu_component(admin_client):
    """Test CPU component health structure."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    cpu = data['components']['cpu']

    assert 'status' in cpu
    if cpu['status'] in ['low', 'normal', 'high']:
        assert 'load_percent' in cpu
        assert isinstance(cpu['load_percent'], (int, float))
        assert 0 <= cpu['load_percent'] <= 100
    elif cpu['status'] == 'error':
        assert 'error' in cpu


def test_health_overall_status_logic(admin_client):
    """Test that overall status is calculated correctly based on components."""
    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    overall_status = data['status']
    components = data['components']

    # Check if any component is critical
    has_critical = any(
        comp.get('status') in ['critical', 'error']
        for comp in components.values()
    )

    # Check if any component is warning
    has_warning = any(
        comp.get('status') in ['warning', 'high']
        for comp in components.values()
    )

    if has_critical:
        assert overall_status == 'critical'
    elif has_warning:
        assert overall_status == 'warning'
    else:
        # Should be healthy if no critical or warning
        assert overall_status == 'healthy'


@patch('psutil.disk_usage')
def test_health_disk_critical_threshold(mock_disk, admin_client):
    """Test that disk usage above 95% is marked as critical."""
    # Mock disk usage at 96%
    mock_disk.return_value = MagicMock(
        free=40 * 1024**3,  # 40 GB free
        total=1000 * 1024**3,  # 1000 GB total
        percent=96.0
    )

    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    disk = data['components']['disk']
    assert disk['status'] == 'critical'


@patch('psutil.disk_usage')
def test_health_disk_warning_threshold(mock_disk, admin_client):
    """Test that disk usage between 85-95% is marked as warning."""
    # Mock disk usage at 90%
    mock_disk.return_value = MagicMock(
        free=100 * 1024**3,  # 100 GB free
        total=1000 * 1024**3,  # 1000 GB total
        percent=90.0
    )

    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    disk = data['components']['disk']
    assert disk['status'] == 'warning'


@patch('psutil.virtual_memory')
def test_health_memory_critical_threshold(mock_mem, admin_client):
    """Test that memory usage above 90% is marked as critical."""
    # Mock memory usage at 92%
    mock_mem.return_value = MagicMock(
        used=7372 * 1024 * 1024,  # 7372 MB
        total=8192 * 1024 * 1024,  # 8192 MB
        percent=92.0
    )

    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    memory = data['components']['memory']
    assert memory['status'] == 'critical'


@patch('psutil.cpu_percent')
def test_health_cpu_high_threshold(mock_cpu, admin_client):
    """Test that CPU usage above 80% is marked as high."""
    mock_cpu.return_value = 85.0

    resp = admin_client.get('/api/health/comprehensive')
    data = resp.get_json()

    cpu = data['components']['cpu']
    assert cpu['status'] == 'high'
