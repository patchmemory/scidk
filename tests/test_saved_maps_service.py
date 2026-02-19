"""Unit tests for SavedMapsService."""

import os
import tempfile
import time

import pytest

from scidk.services.saved_maps_service import SavedMapsService, get_saved_maps_service


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    yield path
    os.close(fd)
    os.unlink(path)


@pytest.fixture
def service(temp_db):
    """Create SavedMapsService instance with temporary database."""
    return SavedMapsService(db_path=temp_db)


def test_save_map_creates_new_entry(service):
    """Test that saving a map creates a new database entry."""
    saved_map = service.save_map(
        name="Test Map",
        description="Test description",
        query="MATCH (n) RETURN n",
        filters={"labels": ["File", "Folder"]},
        visualization={"mode": "schema", "layout": "cose"},
        tags="test,demo",
    )

    assert saved_map.id is not None
    assert saved_map.name == "Test Map"
    assert saved_map.description == "Test description"
    assert saved_map.query == "MATCH (n) RETURN n"
    assert saved_map.filters == {"labels": ["File", "Folder"]}
    assert saved_map.visualization == {"mode": "schema", "layout": "cose"}
    assert saved_map.tags == "test,demo"
    assert saved_map.use_count == 0
    assert saved_map.last_used_at is None


def test_get_map_returns_saved_map(service):
    """Test retrieving a saved map by ID."""
    # Save a map
    saved = service.save_map(
        name="Test Map",
        query="MATCH (n:File) RETURN n LIMIT 10",
    )

    # Retrieve it
    retrieved = service.get_map(saved.id)

    assert retrieved is not None
    assert retrieved.id == saved.id
    assert retrieved.name == "Test Map"
    assert retrieved.query == "MATCH (n:File) RETURN n LIMIT 10"


def test_get_map_returns_none_for_nonexistent(service):
    """Test that get_map returns None for non-existent ID."""
    result = service.get_map("nonexistent-id")
    assert result is None


def test_list_maps_returns_sorted(service):
    """Test listing maps sorted by updated_at."""
    # Create multiple maps with slight delays
    map1 = service.save_map(name="Map 1")
    time.sleep(0.1)
    map2 = service.save_map(name="Map 2")
    time.sleep(0.1)
    map3 = service.save_map(name="Map 3")

    # List maps (default sort by updated_at DESC)
    maps = service.list_maps()

    assert len(maps) == 3
    assert maps[0].name == "Map 3"  # Most recent
    assert maps[1].name == "Map 2"
    assert maps[2].name == "Map 1"  # Oldest


def test_list_maps_pagination(service):
    """Test pagination in list_maps."""
    # Create 5 maps
    for i in range(5):
        service.save_map(name=f"Map {i}")

    # Get first 2
    maps_page1 = service.list_maps(limit=2, offset=0)
    assert len(maps_page1) == 2

    # Get next 2
    maps_page2 = service.list_maps(limit=2, offset=2)
    assert len(maps_page2) == 2

    # Ensure they're different
    assert maps_page1[0].id != maps_page2[0].id


def test_update_map(service):
    """Test updating a map's properties."""
    # Create map
    saved = service.save_map(name="Original Name", description="Original description")

    original_updated_at = saved.updated_at

    # Small delay to ensure updated_at changes
    time.sleep(0.1)

    # Update map
    updated = service.update_map(
        saved.id,
        name="Updated Name",
        description="Updated description",
        tags="updated",
    )

    assert updated is not None
    assert updated.id == saved.id
    assert updated.name == "Updated Name"
    assert updated.description == "Updated description"
    assert updated.tags == "updated"
    assert updated.updated_at > original_updated_at


def test_update_nonexistent_map_returns_none(service):
    """Test that updating non-existent map returns None."""
    result = service.update_map("nonexistent-id", name="New Name")
    assert result is None


def test_delete_map(service):
    """Test deleting a map."""
    # Create map
    saved = service.save_map(name="To Delete")

    # Delete it
    deleted = service.delete_map(saved.id)
    assert deleted is True

    # Verify it's gone
    retrieved = service.get_map(saved.id)
    assert retrieved is None


def test_delete_nonexistent_map_returns_false(service):
    """Test that deleting non-existent map returns False."""
    result = service.delete_map("nonexistent-id")
    assert result is False


def test_track_usage(service):
    """Test tracking map usage updates counters."""
    # Create map
    saved = service.save_map(name="Test Map")

    assert saved.use_count == 0
    assert saved.last_used_at is None

    # Track usage
    time.sleep(0.1)  # Ensure timestamp changes
    tracked = service.track_usage(saved.id)
    assert tracked is True

    # Retrieve and verify
    updated = service.get_map(saved.id)
    assert updated.use_count == 1
    assert updated.last_used_at is not None
    assert updated.last_used_at > saved.created_at


def test_track_usage_increments(service):
    """Test that tracking usage multiple times increments counter."""
    saved = service.save_map(name="Test Map")

    # Track multiple times
    service.track_usage(saved.id)
    service.track_usage(saved.id)
    service.track_usage(saved.id)

    # Verify count
    updated = service.get_map(saved.id)
    assert updated.use_count == 3


def test_filters_serialization(service):
    """Test that complex filters are properly serialized/deserialized."""
    complex_filters = {
        "labels": ["File", "Folder", "Sample"],
        "rel_types": ["CONTAINS", "HAS_TYPE"],
        "property_filters": [
            {
                "label": "Sample",
                "property": "type",
                "operator": "=",
                "value": "blood",
                "data_type": "string",
            }
        ],
    }

    saved = service.save_map(name="Complex Filters", filters=complex_filters)

    retrieved = service.get_map(saved.id)
    assert retrieved.filters == complex_filters


def test_visualization_serialization(service):
    """Test that visualization settings are properly serialized/deserialized."""
    viz_settings = {
        "mode": "hybrid",
        "layout": "breadthfirst",
        "node_size": 1.5,
        "edge_width": 2.0,
        "high_contrast": True,
    }

    saved = service.save_map(name="Custom Viz", visualization=viz_settings)

    retrieved = service.get_map(saved.id)
    assert retrieved.visualization == viz_settings


def test_empty_filters_and_visualization(service):
    """Test that maps can be saved without filters or visualization."""
    saved = service.save_map(name="Minimal Map")

    retrieved = service.get_map(saved.id)
    assert retrieved.filters == {}
    assert retrieved.visualization == {}


def test_get_saved_maps_service_singleton():
    """Test that get_saved_maps_service returns singleton instance."""
    service1 = get_saved_maps_service()
    service2 = get_saved_maps_service()

    assert service1 is service2


def test_list_maps_sort_by_name(service):
    """Test sorting maps by name."""
    service.save_map(name="Zebra Map")
    service.save_map(name="Alpha Map")
    service.save_map(name="Beta Map")

    maps = service.list_maps(sort_by="name", order="ASC")

    assert maps[0].name == "Alpha Map"
    assert maps[1].name == "Beta Map"
    assert maps[2].name == "Zebra Map"


def test_list_maps_sort_by_use_count(service):
    """Test sorting maps by use count."""
    map1 = service.save_map(name="Map 1")
    map2 = service.save_map(name="Map 2")
    map3 = service.save_map(name="Map 3")

    # Track different usage counts
    service.track_usage(map2.id)
    service.track_usage(map2.id)
    service.track_usage(map2.id)  # 3 uses

    service.track_usage(map1.id)  # 1 use

    # map3 has 0 uses

    maps = service.list_maps(sort_by="use_count", order="DESC")

    assert maps[0].name == "Map 2"  # 3 uses
    assert maps[1].name == "Map 1"  # 1 use
    assert maps[2].name == "Map 3"  # 0 uses


def test_to_dict(service):
    """Test SavedMap.to_dict() method."""
    saved = service.save_map(
        name="Test Map",
        description="Description",
        query="MATCH (n) RETURN n",
        filters={"labels": ["File"]},
        visualization={"mode": "schema"},
        tags="test",
    )

    dict_repr = saved.to_dict()

    assert dict_repr["id"] == saved.id
    assert dict_repr["name"] == "Test Map"
    assert dict_repr["description"] == "Description"
    assert dict_repr["query"] == "MATCH (n) RETURN n"
    assert dict_repr["filters"] == {"labels": ["File"]}
    assert dict_repr["visualization"] == {"mode": "schema"}
    assert dict_repr["tags"] == "test"
    assert dict_repr["use_count"] == 0
    assert dict_repr["last_used_at"] is None
    assert "created_at" in dict_repr
    assert "updated_at" in dict_repr
