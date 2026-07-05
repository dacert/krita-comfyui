import json

import pytest

from krita_comfyui.config import DEFAULT_URL, Config, WorkflowConfig, WorkflowInput


@pytest.fixture
def sample_cfg_dict():
    """A minimal but realistic configuration dictionary."""
    return {
        "logger": False,
        "comfyui_url": "http://example.com",
        "workflows": [
            {
                "workflow_name": "test.json",
                "inputs": {
                    "prompt": {"node_id": "1", "property": "value"},
                    # Explicitly omit 'negative_prompt' to test optional handling
                },
            }
        ],
    }


@pytest.fixture
def sample_cfg_file(tmp_path, sample_cfg_dict):
    """Create a temporary config file with the sample dictionary."""
    p = tmp_path / "krita_comfyui.config"
    p.write_text(json.dumps(sample_cfg_dict), encoding="utf-8")
    return p


def test_load_valid_config(sample_cfg_file, sample_cfg_dict):
    cfg = Config.load(sample_cfg_file)
    assert cfg.logger is False
    assert cfg.comfyui_url == "http://example.com"
    assert len(cfg.workflows) == 1

    wf = cfg.workflows[0]
    assert isinstance(wf, WorkflowConfig)
    assert wf.workflow_name == "test.json"

    inp_prompt = wf.inputs["prompt"]
    assert isinstance(inp_prompt, WorkflowInput)
    assert inp_prompt.node_id == "1"
    assert inp_prompt.property == "value"

    # Optional field should be missing
    assert "negative_prompt" not in wf.inputs


def test_save_and_reload(tmp_path):
    cfg_original = Config(
        logger=True,
        comfyui_url="http://save.test",
        workflows=[
            WorkflowConfig(
                workflow_name="save.json",
                inputs={"prompt": WorkflowInput("42", None)},
            )
        ],
    )

    save_path = tmp_path / "saved_krita_comfyui.config"
    cfg_original.save(save_path)

    # Ensure file was written
    assert save_path.exists()
    loaded_cfg = Config.load(save_path)
    assert loaded_cfg == cfg_original


def test_load_or_create_missing_file(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"

    cfg = Config.load_or_create(missing_path)

    # Should create default configuration
    assert cfg.logger is False
    assert cfg.comfyui_url == DEFAULT_URL
    assert cfg.workflows == []
    assert cfg.timeout_minutes == 5

    # File should now exist with the default content
    assert missing_path.exists()
    data = json.loads(missing_path.read_text(encoding="utf-8"))
    assert data["logger"] is False
    assert data["comfyui_url"] == DEFAULT_URL
    assert data["workflows"] == []
    assert data["timeout_minutes"] == 5


def test_load_or_create_corrupted_json(tmp_path, sample_cfg_file):
    # Corrupt the file by writing invalid JSON
    corrupted = tmp_path / "corrupt.json"
    corrupted.write_text("{ not a json", encoding="utf-8")

    cfg = Config.load_or_create(corrupted)

    # Should fallback to default
    assert cfg.logger is False
    assert cfg.comfyui_url == DEFAULT_URL
    assert cfg.workflows == []

    # The file should now contain the default config
    data = json.loads(corrupted.read_text(encoding="utf-8"))
    assert data["logger"] is False
    assert data["comfyui_url"] == DEFAULT_URL


def test_missing_optional_fields_in_workflow(tmp_path):
    """Test that missing optional fields are handled gracefully."""
    cfg_dict = {
        "logger": True,
        "workflows": [
            {
                # Missing comfyui_url; should default to DEFAULT_URL
                "workflow_name": "missing_url.json",
                "inputs": {},
            }
        ],
    }

    p = tmp_path / "partial_krita_comfyui.config"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    assert cfg.comfyui_url == DEFAULT_URL
    assert len(cfg.workflows) == 1
    wf = cfg.workflows[0]
    assert wf.workflow_name == "missing_url.json"
    assert wf.inputs == {}


def test_null_values_in_inputs(tmp_path):
    """Inputs can contain null node_id/property; ensure they're preserved."""
    cfg_dict = {
        "logger": False,
        "workflows": [
            {
                "workflow_name": "null_input.json",
                "inputs": {"some_field": {"node_id": None, "property": None}},
            }
        ],
    }

    p = tmp_path / "null_inputs.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    wf = cfg.workflows[0]
    inp = wf.inputs["some_field"]
    assert inp.node_id is None
    assert inp.property is None

    # When saving, the nulls should be preserved
    out_path = tmp_path / "output.json"
    cfg.save(out_path)
    data_out = json.loads(out_path.read_text(encoding="utf-8"))
    assert data_out["workflows"][0]["inputs"]["some_field"]["node_id"] is None
    assert data_out["workflows"][0]["inputs"]["some_field"]["property"] is None


def test_empty_workflows_list(tmp_path):
    """Ensure that an empty workflows list is handled correctly."""
    cfg_dict = {"logger": False, "comfyui_url": "http://example.com", "workflows": []}
    p = tmp_path / "empty_workflows.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    assert cfg.workflows == []

    # Save and reload to confirm persistence
    out_path = tmp_path / "out_empty.json"
    cfg.save(out_path)
    loaded_cfg = Config.load(out_path)
    assert loaded_cfg.workflows == []


@pytest.mark.parametrize(
    ("invalid_json", "error_message"),
    [
        ("{", "Expecting property name"),  # truncated JSON
        ('{"logger": true, "workflows": [}', "Expecting value"),  # malformed array
        ("not a json at all", "Expecting value"),
    ],
)
def test_load_invalid_json(tmp_path, invalid_json, error_message):
    p = tmp_path / "bad.json"
    p.write_text(invalid_json, encoding="utf-8")
    with pytest.raises(json.JSONDecodeError) as excinfo:
        Config.load(p)
    assert error_message in str(excinfo.value)


def test_workflow_input_missing_properties(tmp_path):
    """If a workflow input dict is missing node_id or property keys, defaults to None."""
    cfg_dict = {
        "workflows": [
            {
                "workflow_name": "missing_keys.json",
                "inputs": {"field1": {"node_id": "99"}},  # property omitted
            }
        ]
    }
    p = tmp_path / "missing_keys.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    wf = cfg.workflows[0]
    inp = wf.inputs["field1"]
    assert inp.node_id == "99"
    assert inp.property is None  # default for missing key


def test_workflow_input_extra_keys(tmp_path):
    """Extra keys in the input dict should be ignored."""
    cfg_dict = {
        "workflows": [
            {
                "workflow_name": "extra_keys.json",
                "inputs": {"field1": {"node_id": "99", "property": "text", "foo": "bar"}},
            }
        ]
    }
    p = tmp_path / "extra_keys.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    wf = cfg.workflows[0]
    inp = wf.inputs["field1"]
    assert inp.node_id == "99"
    assert inp.property == "text"


def test_timeout_default_when_missing(tmp_path):
    """When timeout_minutes is missing, default to 5 minutes."""
    cfg_dict = {"logger": False, "comfyui_url": "http://example.com", "workflows": []}
    p = tmp_path / "no_timeout.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    assert cfg.timeout_minutes == 5


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (0, 1),  # below min -> clamped to 1
        (1, 1),  # boundary
        (30, 30),  # mid-range
        (60, 60),  # boundary
        (61, 60),  # above max -> clamped to 60
        (999, 60),  # far above max -> clamped to 60
    ],
)
def test_timeout_clamped_to_range(tmp_path, raw_value, expected):
    """Values outside [1, 60] are clamped on load."""
    cfg_dict = {
        "logger": False,
        "comfyui_url": "http://example.com",
        "workflows": [],
        "timeout_minutes": raw_value,
    }
    p = tmp_path / "clamped_timeout.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")

    cfg = Config.load(p)
    assert cfg.timeout_minutes == expected


def test_timeout_persistence_roundtrip(tmp_path):
    """timeout_minutes is saved to disk and reloaded with the same value."""
    cfg = Config(
        logger=False,
        comfyui_url="http://example.com",
        workflows=[],
        timeout_minutes=15,
    )
    out_path = tmp_path / "persist_timeout.json"
    cfg.save(out_path)

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["timeout_minutes"] == 15

    loaded = Config.load(out_path)
    assert loaded.timeout_minutes == 15


# End of test suite
