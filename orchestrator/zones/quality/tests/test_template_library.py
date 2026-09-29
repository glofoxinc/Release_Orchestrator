"""Tests for the reusable template library."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from template_library import (
    BUILTIN_TEMPLATES,
    Template,
    apply_template,
    capture_from_draft,
    default_templates_dir,
    delete_template,
    ensure_directory,
    list_templates,
    load_template,
    save_template,
)


class TestBuiltinTemplates:
    def test_shipped_templates_have_required_names(self):
        names = {t.name for t in BUILTIN_TEMPLATES}
        assert "emergency-hotfix" in names
        assert "standard-monthly-glofox" in names
        assert "major-feature-release" in names
        assert "custom-client-deployment" in names
        assert "semantic-model-refactor" in names

    def test_each_template_has_data(self):
        for t in BUILTIN_TEMPLATES:
            assert t.data, f"{t.name} should have data"

    def test_each_template_has_tags(self):
        for t in BUILTIN_TEMPLATES:
            assert isinstance(t.tags, list) and t.tags

    def test_yaml_round_trip(self):
        for t in BUILTIN_TEMPLATES:
            import yaml
            data = yaml.safe_load(t.to_yaml())
            rebuilt = Template.from_dict(data)
            assert rebuilt.name == t.name


class TestTemplateCrud:
    def test_save_and_load_template(self, tmp_path):
        tpl = Template(name="my-tpl", description="d", tags=["a"], data={"k": "v"})
        save_template(tpl, tmp_path)
        loaded = load_template("my-tpl", tmp_path)
        assert loaded.name == "my-tpl"
        assert loaded.description == "d"
        assert loaded.tags == ["a"]
        assert loaded.data == {"k": "v"}

    def test_save_refuses_overwrite_when_flag_false(self, tmp_path):
        tpl = Template(name="x", data={"k": "v"})
        save_template(tpl, tmp_path)
        with pytest.raises(FileExistsError):
            save_template(tpl, tmp_path, overwrite=False)

    def test_delete_template(self, tmp_path):
        save_template(Template(name="to-delete"), tmp_path)
        assert delete_template("to-delete", tmp_path) is True
        assert delete_template("to-delete", tmp_path) is False

    def test_list_includes_user_and_builtins(self, tmp_path):
        save_template(Template(name="custom-one"), tmp_path)
        names = [t.name for t in list_templates(tmp_path)]
        assert "custom-one" in names
        assert "emergency-hotfix" in names

    def test_user_template_overrides_builtin(self, tmp_path):
        save_template(
            Template(name="emergency-hotfix", description="overridden"), tmp_path
        )
        loaded = load_template("emergency-hotfix", tmp_path)
        assert loaded.description == "overridden"

    def test_load_unknown_raises(self, tmp_path):
        with pytest.raises(KeyError):
            load_template("nonexistent", tmp_path)

    def test_malformed_templates_are_skipped(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: valid: yaml: template", encoding="utf-8")
        result = list_templates(tmp_path)
        assert any(t.name for t in result)  # still returns the built-ins


class TestValidation:
    def test_invalid_names_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            save_template(Template(name="has spaces"), tmp_path)

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            Template.from_dict({"name": "", "data": {}})

    def test_non_mapping_rejected(self):
        with pytest.raises(ValueError):
            Template.from_dict([])  # type: ignore[arg-type]

    def test_tags_string_is_normalized(self):
        tpl = Template.from_dict({"name": "x", "tags": "a, b ,c", "data": {}})
        assert tpl.tags == ["a", "b", "c"]

    def test_invalid_tags_type_rejected(self):
        with pytest.raises(ValueError):
            Template.from_dict({"name": "x", "tags": 123, "data": {}})

    def test_non_mapping_data_rejected(self):
        with pytest.raises(ValueError):
            Template.from_dict({"name": "x", "tags": ["a"], "data": ["bad"]})


class TestCaptureFromDraft:
    def test_captures_default_keys(self):
        draft = {
            "priority": "Medium",
            "impl_plan": "ignored",  # not in default keys
            "test_plan": "validate",
            "secret_token": "***",
        }
        tpl = capture_from_draft("captured", draft)
        assert "priority" in tpl.data
        assert "test_plan" in tpl.data
        assert "secret_token" not in tpl.data

    def test_explicit_include_keys(self):
        draft = {"a": 1, "b": 2, "c": 3}
        tpl = capture_from_draft("c", draft, include_keys=["a", "c"])
        assert tpl.data == {"a": 1, "c": 3}

    def test_invalid_name_rejected(self):
        with pytest.raises(ValueError):
            capture_from_draft("has space", {})

    def test_tags_preserved(self):
        tpl = capture_from_draft("x", {}, tags=["a", "b"])
        assert tpl.tags == ["a", "b"]


class TestApplyTemplate:
    def test_empty_fields_are_populated(self):
        draft = {"priority": "", "impact": None}
        tpl = Template(name="x", data={"priority": "High", "impact": "Moderate", "urgency": "Low"})
        merged = apply_template(draft, tpl)
        assert merged["priority"] == "High"
        assert merged["impact"] == "Moderate"
        assert merged["urgency"] == "Low"

    def test_existing_values_not_overwritten_by_default(self):
        draft = {"priority": "Medium"}
        tpl = Template(name="x", data={"priority": "High"})
        merged = apply_template(draft, tpl)
        assert merged["priority"] == "Medium"

    def test_overwrite_flag_forces_override(self):
        draft = {"priority": "Medium"}
        tpl = Template(name="x", data={"priority": "High"})
        merged = apply_template(draft, tpl, overwrite=True)
        assert merged["priority"] == "High"

    def test_does_not_mutate_input(self):
        draft = {"a": "1"}
        tpl = Template(name="x", data={"a": "2", "b": "3"})
        merged = apply_template(draft, tpl, overwrite=True)
        assert draft == {"a": "1"}
        assert merged == {"a": "2", "b": "3"}


class TestDefaultDirectory:
    def test_env_override_respected(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JRT_TEMPLATES_DIR", str(tmp_path))
        assert default_templates_dir() == tmp_path.resolve()

    def test_ensure_directory_creates_path(self, tmp_path):
        target = tmp_path / "nested" / "deep"
        result = ensure_directory(target)
        assert result.is_dir()
        assert result == target
