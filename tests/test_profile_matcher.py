from scidk.core.profile_matcher import match


def _file(name, path=None, size=10):
    return {"Name": name, "Path": path or name, "Size": size, "IsDir": False}


TIFF_PROFILE = {
    "profile_id": "tiff_collection",
    "trigger": {
        "extensions": [".tif", ".tiff"],
        "filename_pattern": r".*\.(tif|tiff)$",
    },
    "siblings": [
        {
            "group": "tiff_files",
            "required": True,
            "type": "file",
            "min_count": 1,
            "patterns": [r".*\.(tif|tiff)$"],
        }
    ],
}

FILE_COLLECTION_PROFILE = {
    "profile_id": "file_collection",
    "trigger": {"extensions": [], "filename_pattern": ".*"},
}

IMAGE_SEQUENCE_PROFILE = {
    "profile_id": "image_sequence",
    "trigger": {
        "extensions": [".tif", ".tiff"],
        "filename_pattern": r".*\d{3,}\.(tif|tiff)$",
    },
    "siblings": [
        {
            "group": "numbered_images",
            "required": True,
            "type": "file",
            "min_count": 3,
            "patterns": [r".*\d{3,}\.(tif|tiff)$"],
        }
    ],
}


def test_trigger_match():
    entries = [_file("scan001.tif"), _file("notes.txt")]
    res = match("/data/scan", entries, TIFF_PROFILE)
    assert res["matched"] is True
    assert res["trigger_file"] == "scan001.tif"
    assert res["matched_groups"]["tiff_files"] == ["scan001.tif"]


def test_trigger_no_match():
    entries = [_file("notes.txt"), _file("data.csv")]
    res = match("/data/scan", entries, TIFF_PROFILE)
    assert res["matched"] is False
    assert res["trigger_file"] is None


def test_required_sibling_present():
    entries = [_file("a001.tif"), _file("a002.tif"), _file("a003.tif")]
    res = match("/data/seq", entries, IMAGE_SEQUENCE_PROFILE)
    assert res["matched"] is True
    assert len(res["matched_groups"]["numbered_images"]) == 3


def test_required_sibling_absent():
    # Trigger matches (one numbered tiff) but min_count of 3 is not met.
    entries = [_file("a001.tif"), _file("plain.tif")]
    res = match("/data/seq", entries, IMAGE_SEQUENCE_PROFILE)
    assert res["matched"] is False


def test_empty_trigger_extensions_matches_any_directory():
    entries = [_file("whatever.bin"), {"Name": "sub", "Path": "sub", "IsDir": True}]
    res = match("/data/anything", entries, FILE_COLLECTION_PROFILE)
    assert res["matched"] is True
