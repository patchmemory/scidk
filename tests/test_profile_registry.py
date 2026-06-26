import pathlib

from scidk.core.profile_registry import ProfileRegistry

PROFILES_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scidk"
    / "interpreters"
    / "profiles"
)


def _loaded_registry():
    reg = ProfileRegistry()
    reg.load(PROFILES_DIR)
    return reg


def test_load_finds_all_profiles():
    reg = _loaded_registry()
    for pid in ("file_collection", "tiff_collection", "csv_collection", "image_sequence"):
        assert reg.get(pid) is not None, f"missing profile {pid}"


def test_get_returns_none_for_unknown():
    reg = _loaded_registry()
    assert reg.get("does_not_exist") is None


def test_inheritance_depth():
    reg = _loaded_registry()
    # file_collection has no parent -> depth 0
    assert reg.get("file_collection")["_depth"] == 0
    # tiff_collection inherits file_collection -> depth 1
    assert reg.get("tiff_collection")["_depth"] == 1
    # csv_collection inherits file_collection -> depth 1
    assert reg.get("csv_collection")["_depth"] == 1
    # image_sequence inherits tiff_collection -> depth 2
    assert reg.get("image_sequence")["_depth"] == 2


def test_ordered_profiles_shallowest_first():
    reg = _loaded_registry()
    depths = [p["_depth"] for p in reg.ordered_profiles()]
    assert depths == sorted(depths), f"not shallowest-first: {depths}"
    # base profile must come before any that inherit from it
    order = [p["profile_id"] for p in reg.ordered_profiles()]
    assert order.index("file_collection") < order.index("tiff_collection")
    assert order.index("tiff_collection") < order.index("image_sequence")


def test_load_missing_dir_is_safe(tmp_path):
    reg = ProfileRegistry()
    reg.load(tmp_path / "nope")
    assert reg.ordered_profiles() == []
