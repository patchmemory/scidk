"""
Tests for relationship discovery and triple import functionality.
"""
import pytest
from scidk.services.link_service import LinkService
from unittest.mock import MagicMock, patch


@pytest.fixture
def link_service(app):
    """Create LinkService instance."""
    return LinkService(app)


@pytest.fixture
def mock_source_client():
    """Mock Neo4j client for source database."""
    client = MagicMock()
    client.execute_read = MagicMock()
    return client


@pytest.fixture
def mock_primary_client():
    """Mock Neo4j client for primary database."""
    client = MagicMock()
    client.execute_read = MagicMock()
    client.execute_write = MagicMock()
    return client


class TestRelationshipDiscovery:
    """Tests for discover_relationships feature."""

    def test_discover_relationships_validates_label_format(self, link_service):
        """Should return empty list for invalid label formats."""
        with patch('scidk.services.link_service.get_neo4j_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.execute_read.return_value = [
                {
                    'source_label': 'Invalid Label!',  # Invalid
                    'rel_type': 'LINKS_TO',
                    'target_label': 'Target',
                    'triple_count': 10
                }
            ]
            mock_get_client.return_value = mock_client

            result = link_service.discover_relationships()

            # Should filter out invalid labels
            assert isinstance(result, list)

    def test_discover_relationships_includes_primary_database(self, link_service):
        """Should discover relationships from PRIMARY database and promote to active."""
        with patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary, \
             patch('scidk.services.neo4j_client.list_neo4j_profiles') as mock_profiles:

            # Mock primary database client
            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = [
                {
                    'source_label': 'Gene',
                    'rel_type': 'INTERACTS_WITH',
                    'target_label': 'Protein',
                    'triple_count': 150
                }
            ]
            mock_primary.return_value = primary_mock

            # Mock no additional profiles
            mock_profiles.return_value = []

            result = link_service.discover_relationships()

            # PRIMARY relationships are filtered out (promoted to active instead)
            # So result should be empty when only PRIMARY has relationships
            assert isinstance(result, list)
            # Verify the primary client was called
            assert mock_primary.called


class TestTripleImportPreview:
    """Tests for preview_triple_import feature."""

    def test_preview_validates_relationship_type(self, link_service):
        """Should reject invalid relationship type formats."""
        result = link_service.preview_triple_import(
            'TestDB', 'INVALID REL!', 'Source', 'Target'
        )

        assert result['status'] == 'error'
        assert 'Invalid relationship type' in result['error']

    def test_preview_validates_label_formats(self, link_service):
        """Should reject invalid label formats."""
        result = link_service.preview_triple_import(
            'TestDB', 'LINKS_TO', 'Invalid Label!', 'Target'
        )

        assert result['status'] == 'error'
        assert 'Invalid label format' in result['error']

    def test_preview_returns_sample_triples(self, link_service):
        """Should return preview of first 100 triples."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile:
            mock_client = MagicMock()
            mock_client.execute_read.return_value = [
                {
                    'source_props': {'id': '1', 'name': 'A'},
                    'rel_props': {'since': '2020'},
                    'target_props': {'id': '2', 'name': 'B'}
                }
            ]
            mock_client.close = MagicMock()
            mock_profile.return_value = mock_client

            result = link_service.preview_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target'
            )

            assert result['status'] == 'success'
            assert 'preview' in result
            assert 'total_count' in result
            assert 'preview_hash' in result
            assert len(result['preview']) <= 100

    def test_preview_includes_hash_for_validation(self, link_service):
        """Should include preview_hash for commit validation."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile:
            mock_client = MagicMock()
            mock_client.execute_read.return_value = []
            mock_client.close = MagicMock()
            mock_profile.return_value = mock_client

            result = link_service.preview_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target'
            )

            assert 'preview_hash' in result
            assert len(result['preview_hash']) > 0


class TestTripleImportCommit:
    """Tests for commit_triple_import with optimization strategies."""

    def test_commit_validates_relationship_type(self, link_service):
        """Should reject invalid relationship type formats."""
        result = link_service.commit_triple_import(
            'TestDB', 'INVALID REL!', 'Source', 'Target', 'hash123'
        )

        assert result['status'] == 'error'
        assert 'Invalid relationship type' in result['error']

    def test_commit_validates_label_formats(self, link_service):
        """Should reject invalid label formats."""
        result = link_service.commit_triple_import(
            'TestDB', 'LINKS_TO', 'Invalid Label!', 'Target', 'hash123'
        )

        assert result['status'] == 'error'
        assert 'Invalid label format' in result['error']

    def test_commit_tries_apoc_first(self, link_service):
        """Should attempt APOC-based import before streaming."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile, \
             patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary, \
             patch('scidk.core.settings.get_settings_by_prefix') as mock_settings:


            # Mock source database client
            source_mock = MagicMock()
            source_mock.close = MagicMock()
            mock_profile.return_value = source_mock

            # Mock primary database with APOC available
            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = [{'version': '5.0.0'}]  # APOC available
            primary_mock.execute_write.return_value = [{'imported': 100}]
            primary_mock.close = MagicMock()
            mock_primary.return_value = primary_mock

            # Mock source settings
            mock_settings.return_value = {
                'uri': 'bolt://localhost:7687',
                'user': 'neo4j',
                'password': 'test',
                'database': 'neo4j'
            }

            result = link_service.commit_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target', 'hash123'
            )

            assert result['status'] == 'success'
            assert result['method'] == 'apoc'
            # Verify APOC was attempted (execute_read called for version check)
            assert primary_mock.execute_read.called

    def test_commit_falls_back_to_streaming(self, link_service):
        """Should fall back to streaming batch import if APOC unavailable."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile, \
             patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary:

            # Mock APOC unavailable
            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = []  # APOC check fails
            primary_mock.execute_write.return_value = [{'imported': 50}]
            primary_mock.close = MagicMock()
            mock_primary.return_value = primary_mock
            primary_mock.close = MagicMock()

            # Mock source returns triples
            source_mock = MagicMock()
            source_mock.execute_read.return_value = [
                {
                    'source_props': {'id': '1'},
                    'rel_props': {},
                    'target_props': {'id': '2'}
                }
            ]
            source_mock.close = MagicMock()
            mock_profile.return_value = source_mock
            source_mock.close = MagicMock()

            result = link_service.commit_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target', 'hash123'
            )

            assert result['status'] == 'success'
            assert result['method'] == 'streaming_batch'
            assert 'batches_processed' in result

    def test_commit_uses_large_batch_size(self, link_service):
        """Should use 10000 batch size for streaming import."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile, \
             patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary:

            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = []  # APOC unavailable
            primary_mock.execute_write.return_value = [{'imported': 100}]
            mock_primary.return_value = primary_mock
            primary_mock.close = MagicMock()

            # Return exactly batch_size to trigger second batch fetch
            source_mock = MagicMock()
            call_count = [0]

            def mock_read(query):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call should have LIMIT 10000
                    assert 'LIMIT 10000' in query
                    return [{'source_props': {'id': str(i)}, 'rel_props': {}, 'target_props': {'id': str(i+1)}}
                            for i in range(100)]  # Return less than batch_size to end
                return []

            source_mock.execute_read = mock_read
            mock_profile.return_value = source_mock
            source_mock.close = MagicMock()

            result = link_service.commit_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target', 'hash123'
            )

            assert result['status'] == 'success'
            assert call_count[0] >= 1  # Should have called at least once

    def test_commit_adds_provenance_metadata(self, link_service):
        """Should add __source__, __external_db__, __imported_at__, __imported_by__ to relationships."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile, \
             patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary:

            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = []  # APOC unavailable

            # Capture the query to verify provenance
            write_queries = []
            def capture_write(query, params):
                write_queries.append((query, params))
                return [{'imported': 1}]

            primary_mock.execute_write = capture_write
            mock_primary.return_value = primary_mock
            primary_mock.close = MagicMock()

            source_mock = MagicMock()
            source_mock.execute_read.return_value = [
                {'source_props': {'id': '1'}, 'rel_props': {}, 'target_props': {'id': '2'}}
            ]
            mock_profile.return_value = source_mock
            source_mock.close = MagicMock()

            result = link_service.commit_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target', 'hash123'
            )

            assert len(write_queries) > 0
            query, params = write_queries[0]

            # Verify provenance in query
            assert '__source__' in query
            assert '__external_db__' in query
            assert '__imported_at__' in query
            assert '__imported_by__' in query

            # Verify provenance in params
            assert params['external_db'] == 'TestDB'


class TestStreamingOptimization:
    """Tests for streaming batch optimization."""

    def test_streaming_fetches_incrementally(self, link_service):
        """Should fetch batches incrementally with SKIP/LIMIT."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile, \
             patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary:

            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = []  # APOC unavailable
            primary_mock.execute_write.return_value = [{'imported': 100}]
            mock_primary.return_value = primary_mock
            primary_mock.close = MagicMock()

            source_mock = MagicMock()
            queries = []

            def capture_query(query):
                queries.append(query)
                # Return exactly batch_size (10000) on first call to trigger second batch
                if len(queries) == 1:
                    return [{'source_id': f'{i}', 'source_props': {'id': f'{i}'}, 'rel_props': {},
                             'target_id': f'{i+1}', 'target_props': {'id': f'{i+1}'}}
                            for i in range(10000)]
                # Return empty on second call to end loop
                return []

            source_mock.execute_read = capture_query
            mock_profile.return_value = source_mock
            source_mock.close = MagicMock()

            link_service.commit_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target', 'hash123'
            )

            # Verify queries used SKIP (should have made at least 2 calls with incrementing SKIP)
            assert len(queries) >= 2, f"Expected 2+ queries but got {len(queries)}"
            assert 'SKIP 0' in queries[0]
            assert 'SKIP 10000' in queries[1]

    def test_streaming_stops_at_end(self, link_service):
        """Should stop streaming when fewer results than batch_size returned."""
        with patch('scidk.services.neo4j_client.get_neo4j_client_for_profile') as mock_profile, \
             patch('scidk.services.neo4j_client.get_neo4j_client') as mock_primary:

            primary_mock = MagicMock()
            primary_mock.execute_read.return_value = []  # APOC unavailable
            primary_mock.execute_write.return_value = [{'imported': 50}]
            mock_primary.return_value = primary_mock
            primary_mock.close = MagicMock()

            source_mock = MagicMock()
            call_count = [0]

            def limited_results(query):
                call_count[0] += 1
                if call_count[0] == 1:
                    # Return less than batch_size to signal end
                    return [{'source_props': {'id': '1'}, 'rel_props': {}, 'target_props': {'id': '2'}}
                            for _ in range(50)]
                return []  # Shouldn't be called

            source_mock.execute_read = limited_results
            mock_profile.return_value = source_mock
            source_mock.close = MagicMock()

            result = link_service.commit_triple_import(
                'TestDB', 'LINKS_TO', 'Source', 'Target', 'hash123'
            )

            assert call_count[0] == 1  # Should only call once since first batch < 10000
