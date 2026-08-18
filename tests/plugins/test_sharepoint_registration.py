"""Registration tests for the SharePoint plugin (Cycle 3, Task D).

Split out of ``test_sharepoint_intake.py`` so that file covers only the four
``DataSourcePlugin`` contract methods. Template registration is plugin
infrastructure rather than contract behaviour, but it is still the seam the "+"
add-source flow reads, so it keeps its coverage here.
"""
from plugins.sharepoint_intake import config, get_plugin, register_plugin
from plugins.sharepoint_intake.plugin import SharePointPlugin


class MockRegistry:
    def __init__(self):
        self.templates = {}

    def register(self, template_config):
        self.templates[template_config["id"]] = template_config
        return True


class MockApp:
    def __init__(self):
        self.extensions = {"scidk": {"plugin_templates": MockRegistry()}}


def _template():
    app = MockApp()
    metadata = register_plugin(app)
    return metadata, app.extensions["scidk"]["plugin_templates"].templates["sharepoint_intake"]


class TestRegistration:
    def test_registers_under_its_stable_id(self):
        metadata, template = _template()
        assert metadata["name"] == "SharePoint Intake"
        assert template["category"] == "data_import"
        assert template["supports_multiple_instances"] is True
        assert callable(template["handler"])

    def test_advertises_the_plugin_contract(self):
        _metadata, template = _template()
        assert template["plugin_name"] == SharePointPlugin.name
        assert template["source_types"] == SharePointPlugin.source_types
        assert template["reference_mapping"] == config.REFERENCE_MAPPING

    def test_labels_come_from_the_pipeline_not_the_plugin(self):
        # The plugin names no labels of its own any more — the mapping config
        # does, and the Pipeline applies it.
        _metadata, template = _template()
        behavior = template["graph_behavior"]
        assert behavior["can_create_label"] is False
        assert behavior["label_source"] == "pipeline"
        assert behavior["sync_strategy"] == "pipeline"

    def test_config_schema_describes_source_selection_only(self):
        _metadata, template = _template()
        properties = template["config_schema"]["properties"]
        assert set(properties) == {
            "instance_name", "source_path", "sheet", "sample_rows",
            "max_scan_rows", "timeout_sec"}
        # No dry_run / mapping / schedule keys: those are Pipeline concerns.
        assert "dry_run" not in properties

    def test_presets_are_the_two_source_types(self):
        _metadata, template = _template()
        assert set(template["preset_configs"]) == set(SharePointPlugin.source_types)

    def test_handler_performs_discovery(self, tmp_path):
        source = tmp_path / "list.csv"
        source.write_text("A,B\n1,2\n", encoding="utf-8")

        _metadata, template = _template()
        result = template["handler"]({"source_path": str(source)})

        assert result["ok"] is True
        assert result["columns"] == ["A", "B"]
        assert result["row_count"] == 1

    def test_reference_mapping_ships_with_the_plugin(self):
        assert config.mapping_config_path().is_file()

    def test_get_plugin_returns_a_usable_instance(self):
        assert isinstance(get_plugin(), SharePointPlugin)
