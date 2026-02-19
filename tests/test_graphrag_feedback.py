"""
Tests for GraphRAG feedback service and API endpoints.
"""
import json
import time

import pytest

from scidk.services.graphrag_feedback_service import GraphRAGFeedbackService


@pytest.fixture
def feedback_service(tmp_path):
    """Create feedback service with temporary database."""
    db_path = str(tmp_path / "test_feedback.db")
    return GraphRAGFeedbackService(db_path=db_path)


@pytest.fixture
def sample_feedback():
    """Sample feedback data for testing."""
    return {
        'query': 'Find all datasets in my project',
        'entities_extracted': {
            'identifiers': [],
            'labels': ['Dataset'],
            'properties': {},
            'intent': 'find'
        },
        'feedback': {
            'answered_question': True,
            'entity_corrections': None,
            'query_corrections': None,
            'missing_results': None,
            'notes': 'Worked well'
        }
    }


class TestGraphRAGFeedbackService:
    """Test GraphRAG feedback service."""

    def test_add_feedback(self, feedback_service, sample_feedback):
        """Test adding feedback."""
        feedback = feedback_service.add_feedback(
            query=sample_feedback['query'],
            entities_extracted=sample_feedback['entities_extracted'],
            feedback=sample_feedback['feedback']
        )

        assert feedback.id is not None
        assert feedback.query == sample_feedback['query']
        assert feedback.entities_extracted == sample_feedback['entities_extracted']
        assert feedback.feedback == sample_feedback['feedback']
        assert feedback.timestamp > 0

    def test_get_feedback(self, feedback_service, sample_feedback):
        """Test retrieving feedback by ID."""
        # Add feedback
        added = feedback_service.add_feedback(
            query=sample_feedback['query'],
            entities_extracted=sample_feedback['entities_extracted'],
            feedback=sample_feedback['feedback']
        )

        # Retrieve it
        retrieved = feedback_service.get_feedback(added.id)

        assert retrieved is not None
        assert retrieved.id == added.id
        assert retrieved.query == sample_feedback['query']

    def test_list_feedback(self, feedback_service, sample_feedback):
        """Test listing feedback entries."""
        # Add multiple feedback entries
        for i in range(5):
            feedback_service.add_feedback(
                query=f"Query {i}",
                entities_extracted={'labels': []},
                feedback={'answered_question': i % 2 == 0}
            )

        # List all feedback
        feedback_list = feedback_service.list_feedback(limit=10)
        assert len(feedback_list) == 5

        # Filter by answered_question
        positive_feedback = feedback_service.list_feedback(answered_question=True)
        assert len(positive_feedback) == 3  # 0, 2, 4

        negative_feedback = feedback_service.list_feedback(answered_question=False)
        assert len(negative_feedback) == 2  # 1, 3

    def test_feedback_stats(self, feedback_service):
        """Test feedback statistics aggregation."""
        # Add diverse feedback
        feedback_service.add_feedback(
            query='Query 1',
            entities_extracted={'labels': []},
            feedback={'answered_question': True}
        )
        feedback_service.add_feedback(
            query='Query 2',
            entities_extracted={'labels': []},
            feedback={
                'answered_question': False,
                'entity_corrections': {'removed': ['X'], 'added': ['Y']}
            }
        )
        feedback_service.add_feedback(
            query='Query 3',
            entities_extracted={'labels': []},
            feedback={
                'answered_question': True,
                'query_corrections': 'Better query'
            }
        )

        stats = feedback_service.get_feedback_stats()

        assert stats['total_feedback_count'] == 3
        assert stats['answered_yes_count'] == 2
        assert stats['answered_no_count'] == 1
        assert stats['answer_rate'] == 66.7
        assert stats['entity_corrections_count'] == 1
        assert stats['query_corrections_count'] == 1

    def test_entity_corrections(self, feedback_service):
        """Test retrieving entity corrections."""
        feedback_service.add_feedback(
            query='Find dataset ABC',
            entities_extracted={'labels': ['File']},
            feedback={
                'answered_question': False,
                'entity_corrections': {
                    'removed': ['File'],
                    'added': [{'type': 'Dataset', 'value': 'ABC'}]
                }
            }
        )

        corrections = feedback_service.get_entity_corrections(limit=10)

        assert len(corrections) == 1
        assert corrections[0]['query'] == 'Find dataset ABC'
        assert 'File' in str(corrections[0]['extracted'])
        assert corrections[0]['corrections']['removed'] == ['File']

    def test_query_reformulations(self, feedback_service):
        """Test retrieving query reformulations."""
        feedback_service.add_feedback(
            query='Show me all the data',
            entities_extracted={'labels': []},
            feedback={
                'answered_question': False,
                'query_corrections': 'Find all Dataset nodes'
            }
        )

        reformulations = feedback_service.get_query_reformulations(limit=10)

        assert len(reformulations) == 1
        assert reformulations[0]['original_query'] == 'Show me all the data'
        assert reformulations[0]['corrected_query'] == 'Find all Dataset nodes'

    def test_terminology_mappings(self, feedback_service):
        """Test terminology mappings aggregation."""
        feedback_service.add_feedback(
            query='Find experiments',
            entities_extracted={'labels': []},
            feedback={
                'answered_question': True,
                'schema_terminology': {'experiments': 'Assays'}
            }
        )
        feedback_service.add_feedback(
            query='Show samples',
            entities_extracted={'labels': []},
            feedback={
                'answered_question': True,
                'schema_terminology': {'samples': 'Specimens'}
            }
        )

        mappings = feedback_service.get_terminology_mappings()

        assert mappings['experiments'] == 'Assays'
        assert mappings['samples'] == 'Specimens'


class TestFeedbackAPIEndpoints:
    """Test feedback API endpoints."""

    def test_submit_feedback_endpoint(self, client, tmp_path):
        """Test submitting feedback via API."""
        feedback_data = {
            'query': 'Find all files',
            'entities_extracted': {'labels': ['File']},
            'feedback': {
                'answered_question': True
            }
        }

        response = client.post(
            '/api/chat/graphrag/feedback',
            data=json.dumps(feedback_data),
            content_type='application/json'
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert 'feedback_id' in data

    def test_submit_feedback_missing_query(self, client):
        """Test submitting feedback without query."""
        response = client.post(
            '/api/chat/graphrag/feedback',
            data=json.dumps({'feedback': {}}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_list_feedback_endpoint(self, client):
        """Test listing feedback via API."""
        # Submit some feedback first
        for i in range(3):
            client.post(
                '/api/chat/graphrag/feedback',
                data=json.dumps({
                    'query': f'Query {i}',
                    'entities_extracted': {},
                    'feedback': {'answered_question': True}
                }),
                content_type='application/json'
            )

        # List feedback
        response = client.get('/api/chat/graphrag/feedback')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'feedback' in data
        assert len(data['feedback']) == 3

    def test_get_feedback_stats_endpoint(self, client):
        """Test getting feedback statistics via API."""
        # Submit feedback
        client.post(
            '/api/chat/graphrag/feedback',
            data=json.dumps({
                'query': 'Test query',
                'entities_extracted': {},
                'feedback': {'answered_question': True}
            }),
            content_type='application/json'
        )

        # Get stats
        response = client.get('/api/chat/graphrag/feedback/stats')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'total_feedback_count' in data
        assert 'answer_rate' in data
        assert data['total_feedback_count'] >= 1

    def test_get_entity_corrections_endpoint(self, client):
        """Test retrieving entity corrections via API."""
        # Submit feedback with entity corrections
        client.post(
            '/api/chat/graphrag/feedback',
            data=json.dumps({
                'query': 'Find ABC',
                'entities_extracted': {'labels': ['File']},
                'feedback': {
                    'answered_question': False,
                    'entity_corrections': {'removed': ['File'], 'added': ['Dataset']}
                }
            }),
            content_type='application/json'
        )

        # Get entity corrections
        response = client.get('/api/chat/graphrag/feedback/analysis/entities')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'corrections' in data

    def test_get_terminology_mappings_endpoint(self, client):
        """Test retrieving terminology mappings via API."""
        # Submit feedback with terminology mapping
        client.post(
            '/api/chat/graphrag/feedback',
            data=json.dumps({
                'query': 'Find experiments',
                'entities_extracted': {},
                'feedback': {
                    'answered_question': True,
                    'schema_terminology': {'experiments': 'Assays'}
                }
            }),
            content_type='application/json'
        )

        # Get mappings
        response = client.get('/api/chat/graphrag/feedback/analysis/terminology')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'mappings' in data
