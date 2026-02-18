"""
Tests for cross-database instance transfer functionality.

Tests cover:
- Source profile tracking on labels
- Source-aware instance pulling (get_label_instances)
- Source-aware instance counting (get_label_instance_count)
- Transfer to primary functionality (transfer_to_primary)
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from scidk.services.label_service import LabelService


@pytest.fixture
def label_service(app):
    """Create a LabelService instance."""
    return LabelService(app)


@pytest.fixture
def sample_label_with_source(label_service):
    """Create a label with a neo4j_source_profile."""
    label_def = {
        'name': 'TestSourceLabel',
        'properties': [
            {'name': 'id', 'type': 'string', 'required': True},
            {'name': 'name', 'type': 'string', 'required': False}
        ],
        'relationships': [
            {'type': 'RELATES_TO', 'target_label': 'OtherLabel', 'properties': []}
        ],
        'neo4j_source_profile': 'Read-Only Source'
    }
    label_service.save_label(label_def)
    return label_def


@pytest.fixture
def sample_label_without_source(label_service):
    """Create a label without a neo4j_source_profile."""
    label_def = {
        'name': 'TestPrimaryLabel',
        'properties': [
            {'name': 'id', 'type': 'string', 'required': True},
            {'name': 'title', 'type': 'string', 'required': False}
        ],
        'relationships': []
    }
    label_service.save_label(label_def)
    return label_def


class TestSourceProfileTracking:
    """Tests for source profile tracking on labels."""

    def test_save_label_with_source_profile(self, label_service):
        """Test saving a label with a source profile."""
        label_def = {
            'name': 'SourceTrackedLabel',
            'properties': [{'name': 'id', 'type': 'string', 'required': True}],
            'relationships': [],
            'neo4j_source_profile': 'External Database'
        }

        result = label_service.save_label(label_def)

        assert result['name'] == 'SourceTrackedLabel'

        # Retrieve and verify source profile is stored
        retrieved = label_service.get_label('SourceTrackedLabel')
        assert retrieved is not None
        assert retrieved['neo4j_source_profile'] == 'External Database'

    def test_save_label_without_source_profile(self, label_service):
        """Test saving a label without a source profile."""
        label_def = {
            'name': 'NoSourceLabel',
            'properties': [{'name': 'id', 'type': 'string', 'required': True}],
            'relationships': []
        }

        result = label_service.save_label(label_def)

        assert result['name'] == 'NoSourceLabel'

        # Retrieve and verify no source profile
        retrieved = label_service.get_label('NoSourceLabel')
        assert retrieved is not None
        assert retrieved.get('neo4j_source_profile') is None

    def test_update_label_source_profile(self, label_service, sample_label_without_source):
        """Test updating a label to add a source profile."""
        # Update with source profile
        updated_def = {
            'name': 'TestPrimaryLabel',
            'properties': sample_label_without_source['properties'],
            'relationships': sample_label_without_source['relationships'],
            'neo4j_source_profile': 'New Source'
        }

        label_service.save_label(updated_def)

        # Verify update
        retrieved = label_service.get_label('TestPrimaryLabel')
        assert retrieved['neo4j_source_profile'] == 'New Source'


class TestSourceAwareInstanceOperations:
    """Tests for source-aware instance operations."""

    @patch('scidk.core.settings.get_setting')
    @patch('scidk.services.neo4j_client.Neo4jClient')
    def test_get_label_instances_with_source_profile(
        self, mock_neo4j_client_class, mock_get_setting,
        label_service, sample_label_with_source
    ):
        """Test that get_label_instances uses source profile when available."""
        # Mock settings to return profile configuration
        def get_setting_side_effect(key):
            if key == 'neo4j_profile_Read-Only_Source':
                return json.dumps({
                    'uri': 'bolt://remote:7687',
                    'user': 'readonly',
                    'database': 'neo4j'
                })
            elif key == 'neo4j_profile_password_Read-Only_Source':
                return 'password123'
            return None

        mock_get_setting.side_effect = get_setting_side_effect

        # Mock Neo4j client
        mock_client = MagicMock()
        mock_client.execute_read.side_effect = [
            # Instance query results
            [
                {'id': '1', 'properties': {'id': 'obj1', 'name': 'Test 1'}},
                {'id': '2', 'properties': {'id': 'obj2', 'name': 'Test 2'}}
            ],
            # Count query result
            [{'total': 2}]
        ]
        mock_neo4j_client_class.return_value = mock_client

        # Call get_label_instances
        result = label_service.get_label_instances('TestSourceLabel', limit=10, offset=0)

        # Verify source profile client was created
        mock_neo4j_client_class.assert_called_once()
        call_kwargs = mock_neo4j_client_class.call_args[1]
        assert call_kwargs['uri'] == 'bolt://remote:7687'
        assert call_kwargs['user'] == 'readonly'

        # Verify client was connected and closed
        mock_client.connect.assert_called_once()
        mock_client.close.assert_called_once()

        # Verify results
        assert result['status'] == 'success'
        assert len(result['instances']) == 2
        assert result['source_profile'] == 'Read-Only Source'

    @patch('scidk.services.neo4j_client.get_neo4j_client')
    def test_get_label_instances_without_source_profile(
        self, mock_get_client, label_service, sample_label_without_source
    ):
        """Test that get_label_instances uses default client when no source profile."""
        # Mock default client
        mock_client = MagicMock()
        mock_client.execute_read.side_effect = [
            # Instance query results
            [{'id': '1', 'properties': {'id': 'obj1', 'title': 'Title 1'}}],
            # Count query result
            [{'total': 1}]
        ]
        mock_get_client.return_value = mock_client

        # Call get_label_instances
        result = label_service.get_label_instances('TestPrimaryLabel', limit=10, offset=0)

        # Verify default client was used
        mock_get_client.assert_called_once()

        # Verify results
        assert result['status'] == 'success'
        assert len(result['instances']) == 1
        assert result['source_profile'] is None

    @patch('scidk.core.settings.get_setting')
    @patch('scidk.services.neo4j_client.Neo4jClient')
    def test_get_label_instance_count_with_source_profile(
        self, mock_neo4j_client_class, mock_get_setting,
        label_service, sample_label_with_source
    ):
        """Test that get_label_instance_count uses source profile when available."""
        # Mock settings
        def get_setting_side_effect(key):
            if key == 'neo4j_profile_Read-Only_Source':
                return json.dumps({
                    'uri': 'bolt://remote:7687',
                    'user': 'readonly',
                    'database': 'neo4j'
                })
            elif key == 'neo4j_profile_password_Read-Only_Source':
                return 'password123'
            return None

        mock_get_setting.side_effect = get_setting_side_effect

        # Mock Neo4j client
        mock_client = MagicMock()
        mock_client.execute_read.return_value = [{'count': 86}]
        mock_neo4j_client_class.return_value = mock_client

        # Call get_label_instance_count
        result = label_service.get_label_instance_count('TestSourceLabel')

        # Verify source profile client was created
        mock_neo4j_client_class.assert_called_once()

        # Verify client was connected and closed
        mock_client.connect.assert_called_once()
        mock_client.close.assert_called_once()

        # Verify results
        assert result['status'] == 'success'
        assert result['count'] == 86
        assert result['source_profile'] == 'Read-Only Source'


class TestTransferToPrimary:
    """Tests for transfer_to_primary functionality."""

    def test_transfer_without_source_profile(self, label_service, sample_label_without_source):
        """Test that transfer fails when label has no source profile."""
        result = label_service.transfer_to_primary('TestPrimaryLabel', batch_size=10)

        assert result['status'] == 'error'
        assert 'no source profile configured' in result['error'].lower()

    def test_transfer_nonexistent_label(self, label_service):
        """Test that transfer fails for non-existent label."""
        with pytest.raises(ValueError, match="not found"):
            label_service.transfer_to_primary('NonExistentLabel')

    @patch('scidk.core.settings.get_setting')
    @patch('scidk.services.neo4j_client.Neo4jClient')
    @patch('scidk.services.neo4j_client.get_neo4j_client')
    def test_transfer_to_primary_success(
        self, mock_get_primary_client, mock_neo4j_client_class, mock_get_setting,
        label_service, sample_label_with_source
    ):
        """Test successful transfer to primary database."""
        # Mock settings for source profile
        def get_setting_side_effect(key):
            if key == 'neo4j_profile_Read-Only_Source':
                return json.dumps({
                    'uri': 'bolt://source:7687',
                    'user': 'readonly',
                    'database': 'neo4j'
                })
            elif key == 'neo4j_profile_password_Read-Only_Source':
                return 'sourcepass'
            return None

        mock_get_setting.side_effect = get_setting_side_effect

        # Mock source client
        mock_source_client = MagicMock()
        mock_source_client.execute_read.side_effect = [
            # Batch 1: nodes
            [
                {'source_id': 's1', 'props': {'id': 'obj1', 'name': 'Node 1'}},
                {'source_id': 's2', 'props': {'id': 'obj2', 'name': 'Node 2'}}
            ],
            # Batch 2: empty (end of nodes)
            [],
            # Relationships query
            [
                {
                    'source_id': 's1',
                    'source_props': {'id': 'obj1'},
                    'target_props': {'id': 'obj2'},
                    'rel_props': {'since': '2024'}
                }
            ]
        ]

        # Mock primary client
        mock_primary_client = MagicMock()
        mock_primary_client.execute_write.side_effect = [
            # Node 1 merge
            [{'primary_id': 'p1'}],
            # Node 2 merge
            [{'primary_id': 'p2'}],
            # Relationship creation
            None
        ]

        mock_neo4j_client_class.return_value = mock_source_client
        mock_get_primary_client.return_value = mock_primary_client

        # Call transfer_to_primary
        result = label_service.transfer_to_primary('TestSourceLabel', batch_size=10)

        # Verify success
        assert result['status'] == 'success'
        assert result['nodes_transferred'] == 2
        assert result['relationships_transferred'] == 1
        assert result['source_profile'] == 'Read-Only Source'
        assert result['matching_key'] == 'id'  # First required property

        # Verify source client was closed
        mock_source_client.close.assert_called_once()

    @patch('scidk.core.settings.get_setting')
    def test_transfer_with_missing_source_profile(
        self, mock_get_setting, label_service, sample_label_with_source
    ):
        """Test transfer fails gracefully when source profile doesn't exist in settings."""
        mock_get_setting.return_value = None  # Profile not found

        result = label_service.transfer_to_primary('TestSourceLabel')

        assert result['status'] == 'error'
        assert 'not found' in result['error'].lower()


class TestAPIEndpoints:
    """Tests for API endpoints related to cross-database operations."""

    def test_transfer_to_primary_endpoint_without_source(self, client, sample_label_without_source):
        """Test transfer endpoint returns error when label has no source."""
        response = client.post('/api/labels/TestPrimaryLabel/transfer-to-primary')

        assert response.status_code == 500
        data = response.get_json()
        assert data['status'] == 'error'
        assert 'no source profile' in data['error'].lower()

    def test_transfer_to_primary_endpoint_nonexistent_label(self, client):
        """Test transfer endpoint returns 404 for non-existent label."""
        response = client.post('/api/labels/NonExistent/transfer-to-primary')

        assert response.status_code == 404
        data = response.get_json()
        assert data['status'] == 'error'

    @patch('scidk.services.label_service.LabelService.transfer_to_primary')
    def test_transfer_to_primary_endpoint_success(
        self, mock_transfer, client, sample_label_with_source
    ):
        """Test transfer endpoint with successful transfer."""
        mock_transfer.return_value = {
            'status': 'success',
            'nodes_transferred': 50,
            'relationships_transferred': 25,
            'source_profile': 'Read-Only Source',
            'matching_key': 'id'
        }

        response = client.post('/api/labels/TestSourceLabel/transfer-to-primary?batch_size=50')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['nodes_transferred'] == 50
        assert data['relationships_transferred'] == 25

        # Verify batch_size parameter was passed
        mock_transfer.assert_called_once_with('TestSourceLabel', batch_size=50)

    def test_get_label_instances_returns_source_profile(self, client, sample_label_with_source):
        """Test that get instances endpoint returns source_profile in response."""
        with patch('scidk.core.settings.get_setting') as mock_get_setting, \
             patch('scidk.services.neo4j_client.Neo4jClient') as mock_client_class:

            # Mock settings and client
            def get_setting_side_effect(key):
                if key == 'neo4j_profile_Read-Only_Source':
                    return json.dumps({'uri': 'bolt://test:7687', 'user': 'test', 'database': 'neo4j'})
                elif key == 'neo4j_profile_password_Read-Only_Source':
                    return 'pass'
                return None

            mock_get_setting.side_effect = get_setting_side_effect
            mock_client = MagicMock()
            mock_client.execute_read.side_effect = [
                [{'id': '1', 'properties': {'id': 'obj1'}}],
                [{'total': 1}]
            ]
            mock_client_class.return_value = mock_client

            response = client.get('/api/labels/TestSourceLabel/instances?limit=10&offset=0')

            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'success'
            assert data['source_profile'] == 'Read-Only Source'

    def test_get_label_instance_count_returns_source_profile(self, client, sample_label_with_source):
        """Test that instance count endpoint returns source_profile in response."""
        with patch('scidk.core.settings.get_setting') as mock_get_setting, \
             patch('scidk.services.neo4j_client.Neo4jClient') as mock_client_class:

            # Mock settings and client
            def get_setting_side_effect(key):
                if key == 'neo4j_profile_Read-Only_Source':
                    return json.dumps({'uri': 'bolt://test:7687', 'user': 'test', 'database': 'neo4j'})
                elif key == 'neo4j_profile_password_Read-Only_Source':
                    return 'pass'
                return None

            mock_get_setting.side_effect = get_setting_side_effect
            mock_client = MagicMock()
            mock_client.execute_read.return_value = [{'count': 86}]
            mock_client_class.return_value = mock_client

            response = client.get('/api/labels/TestSourceLabel/instance-count')

            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'success'
            assert data['count'] == 86
            assert data['source_profile'] == 'Read-Only Source'
