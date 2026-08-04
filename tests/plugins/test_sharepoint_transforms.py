"""Tests for the SharePoint transform library (Cycle 3, Task C).

The transforms are pure functions, so these tests need no fixtures, no rclone,
and no graph. Each transform is checked against the shared contract:

  * a real value converts correctly,
  * empty input returns the type's empty value and never raises,
  * malformed input raises ``TransformError`` and nothing else.

The core, source-agnostic transforms owned by the Pipeline
(``scidk/pipeline/transforms.py``) are covered at the bottom, along with the
assertion that the plugin's library and the core set stay disjoint.
"""
import pytest

from scidk.pipeline.transforms import (
    CORE_TRANSFORMS,
    TransformError,
    boolean_coerce,
    date_parse,
    integer_coerce,
    lowercase_strip,
    split_delimiter,
)
from plugins.sharepoint_intake.plugin import SharePointPlugin
from plugins.sharepoint_intake.transforms import (
    SHAREPOINT_TRANSFORMS,
    parse_rfc5322,
    parse_rfc5322_list,
    sp_colresolution,
    sp_date,
    sp_multiselect,
    sp_yesno,
)

EMPTY_INPUTS = [None, "", "   ", "\t\n"]


# --------------------------------------------------------------------------- #
# parse_rfc5322                                                               #
# --------------------------------------------------------------------------- #
class TestParseRfc5322:
    def test_name_and_email(self):
        assert parse_rfc5322("Jane Smith <jsmith@mit.edu>") == {
            "name": "Jane Smith", "email": "jsmith@mit.edu"}

    def test_email_is_lowercased_and_name_kept_verbatim(self):
        assert parse_rfc5322("Dr Pat Kim <Pat@MIT.edu>") == {
            "name": "Dr Pat Kim", "email": "pat@mit.edu"}

    def test_quoted_display_name(self):
        assert parse_rfc5322('"Smith, Jane" <j@mit.edu>') == {
            "name": "Smith, Jane", "email": "j@mit.edu"}

    def test_bare_email_has_no_name(self):
        assert parse_rfc5322("jdoe@mit.edu") == {"name": None, "email": "jdoe@mit.edu"}

    def test_display_name_only_has_no_email(self):
        # A raw People-picker value: SharePoint gives a name and no address.
        assert parse_rfc5322("Prof Fallback") == {"name": "Prof Fallback", "email": None}

    @pytest.mark.parametrize("value", EMPTY_INPUTS)
    def test_empty_returns_none_without_raising(self, value):
        assert parse_rfc5322(value) is None

    @pytest.mark.parametrize("value", ["Jane <", "Jane >", "Jane <j@mit.edu"])
    def test_unterminated_address_raises(self, value):
        with pytest.raises(TransformError):
            parse_rfc5322(value)

    def test_empty_address_raises(self):
        with pytest.raises(TransformError):
            parse_rfc5322("Jane <>")

    def test_container_input_raises(self):
        with pytest.raises(TransformError):
            parse_rfc5322({"name": "Jane"})


# --------------------------------------------------------------------------- #
# parse_rfc5322_list                                                          #
# --------------------------------------------------------------------------- #
class TestParseRfc5322List:
    def test_semicolon_separated(self):
        assert parse_rfc5322_list("Alice One <alice@mit.edu>; Bob Two <bob@mit.edu>") == [
            {"name": "Alice One", "email": "alice@mit.edu"},
            {"name": "Bob Two", "email": "bob@mit.edu"},
        ]

    def test_comma_separates_only_when_multiple_addresses_present(self):
        assert parse_rfc5322_list("A One <a@mit.edu>, B Two <b@mit.edu>") == [
            {"name": "A One", "email": "a@mit.edu"},
            {"name": "B Two", "email": "b@mit.edu"},
        ]

    def test_comma_inside_a_single_display_name_is_not_a_separator(self):
        assert parse_rfc5322_list("Smith, Jane <j@mit.edu>") == [
            {"name": "Smith, Jane", "email": "j@mit.edu"}]

    def test_mixed_addressed_and_name_only_entries(self):
        assert parse_rfc5322_list("Alice One <alice@mit.edu>; Bob Two") == [
            {"name": "Alice One", "email": "alice@mit.edu"},
            {"name": "Bob Two", "email": None},
        ]

    def test_blank_entries_are_dropped(self):
        assert parse_rfc5322_list("Alice <a@mit.edu>;;  ") == [
            {"name": "Alice", "email": "a@mit.edu"}]

    @pytest.mark.parametrize("value", EMPTY_INPUTS)
    def test_empty_returns_empty_list_without_raising(self, value):
        assert parse_rfc5322_list(value) == []

    def test_already_split_list_passes_through(self):
        assert parse_rfc5322_list(["Alice <a@mit.edu>", "Bob <b@mit.edu>"]) == [
            {"name": "Alice", "email": "a@mit.edu"},
            {"name": "Bob", "email": "b@mit.edu"},
        ]

    def test_malformed_entry_raises_rather_than_dropping_a_person(self):
        with pytest.raises(TransformError):
            parse_rfc5322_list("Alice <a@mit.edu>; Bob <")


# --------------------------------------------------------------------------- #
# sp_multiselect                                                              #
# --------------------------------------------------------------------------- #
class TestSpMultiselect:
    @pytest.mark.parametrize("value", ["MRI;PET;CT", "MRI;#PET;#CT", "MRI, PET, CT", "MRI; PET;CT"])
    def test_every_delimiter_the_export_produces(self, value):
        assert sp_multiselect(value) == ["MRI", "PET", "CT"]

    def test_single_value(self):
        assert sp_multiselect("MRI") == ["MRI"]

    def test_blank_tokens_are_dropped(self):
        assert sp_multiselect("MRI;;PET;") == ["MRI", "PET"]

    @pytest.mark.parametrize("value", EMPTY_INPUTS)
    def test_empty_returns_empty_list_without_raising(self, value):
        assert sp_multiselect(value) == []

    def test_already_split_list_passes_through(self):
        assert sp_multiselect(["MRI", " PET ", ""]) == ["MRI", "PET"]

    def test_container_input_raises(self):
        with pytest.raises(TransformError):
            sp_multiselect({"a": 1})


# --------------------------------------------------------------------------- #
# sp_date                                                                     #
# --------------------------------------------------------------------------- #
class TestSpDate:
    def test_iso_with_trailing_z(self):
        assert sp_date("2024-03-15T08:30:00Z") == "2024-03-15T08:30:00+00:00"

    def test_date_only_stays_a_date(self):
        assert sp_date("2024-03-15") == "2024-03-15"

    def test_sharepoint_ui_rendering_with_meridiem(self):
        assert sp_date("3/15/2024 8:30 AM") == "2024-03-15T08:30:00"
        assert sp_date("3/15/2024 1:05 PM") == "2024-03-15T13:05:00"

    def test_us_slash_date(self):
        assert sp_date("3/15/2024") == "2024-03-15"

    @pytest.mark.parametrize("value", EMPTY_INPUTS)
    def test_empty_returns_none_without_raising(self, value):
        assert sp_date(value) is None

    @pytest.mark.parametrize("value", ["not a date", "2024-13-45", "15/15/2024"])
    def test_unparseable_raises(self, value):
        with pytest.raises(TransformError):
            sp_date(value)


# --------------------------------------------------------------------------- #
# sp_yesno                                                                    #
# --------------------------------------------------------------------------- #
class TestSpYesNo:
    @pytest.mark.parametrize("value", ["Yes", "yes", "YES", "true", "TRUE", "1", "y"])
    def test_truthy_renderings(self, value):
        assert sp_yesno(value) is True

    @pytest.mark.parametrize("value", ["No", "no", "NO", "false", "FALSE", "0", "n"])
    def test_falsey_renderings(self, value):
        assert sp_yesno(value) is False

    @pytest.mark.parametrize("value", EMPTY_INPUTS)
    def test_empty_returns_none_rather_than_false(self, value):
        # None and False are different answers: "not stated" is not "No".
        assert sp_yesno(value) is None

    @pytest.mark.parametrize("value", ["maybe", "Y/N", "2"])
    def test_non_boolean_raises(self, value):
        with pytest.raises(TransformError):
            sp_yesno(value)


# --------------------------------------------------------------------------- #
# sp_colresolution                                                            #
# --------------------------------------------------------------------------- #
class TestSpColResolution:
    def test_prefers_the_current_sharepoint_value(self):
        row = {"StudyType_sp": "Longitudinal", "StudyType_orig": "Terminal"}
        assert sp_colresolution("StudyType_sp", "StudyType_orig", row) == "Longitudinal"

    def test_falls_back_to_the_legacy_value(self):
        row = {"StudyType_sp": "", "StudyType_orig": "Terminal"}
        assert sp_colresolution("StudyType_sp", "StudyType_orig", row) == "Terminal"

    def test_whitespace_only_is_treated_as_empty(self):
        row = {"StudyType_sp": "   ", "StudyType_orig": "Terminal"}
        assert sp_colresolution("StudyType_sp", "StudyType_orig", row) == "Terminal"

    def test_none_when_both_are_empty(self):
        row = {"StudyType_sp": "", "StudyType_orig": ""}
        assert sp_colresolution("StudyType_sp", "StudyType_orig", row) is None

    def test_none_when_neither_column_exists(self):
        assert sp_colresolution("StudyType_sp", "StudyType_orig", {}) is None

    def test_values_are_stripped(self):
        assert sp_colresolution("a", "b", {"a": "  Pilot  "}) == "Pilot"

    def test_non_mapping_row_raises(self):
        with pytest.raises(TransformError):
            sp_colresolution("a", "b", None)


# --------------------------------------------------------------------------- #
# The library itself                                                          #
# --------------------------------------------------------------------------- #
class TestTransformLibrary:
    EXPECTED = {
        "parse_rfc5322",
        "parse_rfc5322_list",
        "sp_multiselect",
        "sp_date",
        "sp_yesno",
        "sp_colresolution",
    }

    def test_returns_exactly_the_six_sharepoint_transforms(self):
        assert set(SharePointPlugin().transform_library()) == self.EXPECTED

    def test_every_entry_is_callable(self):
        assert all(callable(fn) for fn in SharePointPlugin().transform_library().values())

    def test_excludes_the_core_transforms(self):
        library = SharePointPlugin().transform_library()
        assert not set(library) & set(CORE_TRANSFORMS)

    def test_mutating_the_returned_dict_does_not_corrupt_the_library(self):
        SharePointPlugin().transform_library().clear()
        assert set(SHAREPOINT_TRANSFORMS) == self.EXPECTED


# --------------------------------------------------------------------------- #
# Core transforms (Pipeline-owned; stubs until Cycle 3B finalizes semantics)   #
# --------------------------------------------------------------------------- #
class TestCoreTransforms:
    def test_registry_has_the_five_core_transforms(self):
        assert set(CORE_TRANSFORMS) == {
            "lowercase_strip", "integer_coerce", "boolean_coerce",
            "date_parse", "split_delimiter",
        }
        assert all(callable(fn) for fn in CORE_TRANSFORMS.values())

    def test_happy_paths(self):
        assert lowercase_strip("  MiT.EDU ") == "mit.edu"
        assert integer_coerce("1,234") == 1234
        assert integer_coerce("12.0") == 12
        assert boolean_coerce("on") is True
        assert date_parse("2024-03-15") == "2024-03-15"
        assert date_parse("2024-03-15T08:30:00Z") == "2024-03-15T08:30:00+00:00"
        assert split_delimiter("a;b;;c") == ["a", "b", "c"]

    @pytest.mark.parametrize("value", EMPTY_INPUTS)
    def test_empty_input_never_raises(self, value):
        assert lowercase_strip(value) is None
        assert integer_coerce(value) is None
        assert boolean_coerce(value) is None
        assert date_parse(value) is None
        assert split_delimiter(value) == []

    @pytest.mark.parametrize(
        "fn,value",
        [(integer_coerce, "12.5"), (integer_coerce, "abc"),
         (boolean_coerce, "maybe"), (date_parse, "nope"),
         (lowercase_strip, ["a"])],
    )
    def test_malformed_input_raises_transform_error(self, fn, value):
        with pytest.raises(TransformError):
            fn(value)

    def test_split_delimiter_honours_a_custom_delimiter(self):
        assert split_delimiter("a|b|c", delimiter="|") == ["a", "b", "c"]

    def test_split_delimiter_rejects_an_empty_delimiter(self):
        with pytest.raises(TransformError):
            split_delimiter("a;b", delimiter="")
