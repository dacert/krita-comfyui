import random
from copy import deepcopy

import pytest

from krita_comfyui.prompt_builder import PromptBuilder
from krita_comfyui.config import Config, WorkflowConfig, WorkflowInput


@pytest.fixture
def mock_cfg() -> Config:
    """Create a minimal `Config` instance with one workflow."""
    wf = WorkflowConfig(
        workflow_name="test_wf",
        inputs={
            "prompt": WorkflowInput(node_id="node_prompt", property="text"),
            "seed": WorkflowInput(node_id="node_seed", property="value"),
            "image_loader": WorkflowInput(node_id="node_image", property="path"),
        },
    )
    # Provide required fields for Config
    return Config(logger=False, comfyui_url="http://localhost:8188", workflows=[wf])


@pytest.fixture
def base_api() -> dict:
    """Base API payload that the PromptBuilder will modify."""
    return {
        "node_prompt": {"inputs": {"text": ""}},
        "node_seed": {"inputs": {"value": 0}},
        "node_image": {"inputs": {"path": None}},
        "other_node": {"inputs": {"foo": "bar"}},
    }


def test_build_with_all_inputs(mock_cfg, base_api):
    """Test normal behaviour with all optional arguments supplied."""
    builder = PromptBuilder(cfg=mock_cfg)
    payload = builder.build(
        wf_api=base_api,
        workflow_name="test_wf",
        base_prompt="Hello world!",
        image_input_name="/tmp/img.png",
        seed=12345,
    )

    # Original dict should be unchanged
    assert base_api["node_prompt"]["inputs"]["text"] == ""
    assert base_api["node_seed"]["inputs"]["value"] == 0
    assert base_api["node_image"]["inputs"]["path"] is None

    # Payload should contain the injected values
    assert payload["node_prompt"]["inputs"]["text"] == "Hello world!"
    assert payload["node_seed"]["inputs"]["value"] == 12345
    assert payload["node_image"]["inputs"]["path"] == "/tmp/img.png"

    # Unrelated nodes remain untouched
    assert payload["other_node"]["inputs"]["foo"] == "bar"


def test_build_without_optional_inputs(mock_cfg, base_api, monkeypatch):
    """Test behaviour when optional `image_input_name` and `seed` are omitted."""
    builder = PromptBuilder(cfg=mock_cfg)

    # Patch random.randint to return a deterministic value
    monkeypatch.setattr(random, "randint", lambda a, b: 42)

    payload = builder.build(
        wf_api=base_api,
        workflow_name="test_wf",
        base_prompt="No seed or image",
    )

    assert payload["node_prompt"]["inputs"]["text"] == "No seed or image"
    assert payload["node_seed"]["inputs"]["value"] == 42
    # Image path should remain unchanged (None)
    assert payload["node_image"]["inputs"]["path"] is None


def test_build_unknown_workflow(mock_cfg, base_api):
    """If the workflow name does not exist, the API dict should be returned untouched."""
    builder = PromptBuilder(cfg=mock_cfg)
    result = builder.build(
        wf_api=base_api,
        workflow_name="nonexistent",
        base_prompt="Anything",
    )
    # Should return exactly the same object (identity check)
    assert result is base_api
    # And still unchanged
    assert result["node_prompt"]["inputs"]["text"] == ""


def test_build_missing_input_mapping(mock_cfg, base_api):
    """If a required input mapping key is missing, KeyError should propagate."""
    builder = PromptBuilder(cfg=mock_cfg)
    # Remove the 'seed' mapping from config
    del builder.cfg.workflows[0].inputs["seed"]

    with pytest.raises(KeyError, match="seed"):
        builder.build(wf_api=base_api, workflow_name="test_wf", base_prompt="Missing seed key")


def test_build_payload_is_new_dict(mock_cfg, base_api):
    """Ensure the returned payload is a new dictionary (deep copy)."""
    builder = PromptBuilder(cfg=mock_cfg)
    payload = builder.build(wf_api=base_api, workflow_name="test_wf", base_prompt="Deep copy check")
    # Mutate the payload and verify original stays unchanged
    payload["node_prompt"]["inputs"]["text"] = "Modified"

    assert base_api["node_prompt"]["inputs"]["text"] == ""
    assert payload["node_prompt"]["inputs"]["text"] == "Modified"


def test_build_edge_case_empty_strings_and_zero_seed(mock_cfg, base_api):
    """Test edge cases: empty prompt string and seed=0."""
    builder = PromptBuilder(cfg=mock_cfg)
    payload = builder.build(
        wf_api=base_api,
        workflow_name="test_wf",
        base_prompt="",
        seed=0,
    )
    assert payload["node_prompt"]["inputs"]["text"] == ""
    assert payload["node_seed"]["inputs"]["value"] == 0


def test_build_edge_case_none_image_input(mock_cfg, base_api):
    """If image_input_name is None, the image node should remain unchanged."""
    builder = PromptBuilder(cfg=mock_cfg)
    payload = builder.build(
        wf_api=base_api,
        workflow_name="test_wf",
        base_prompt="No image",
        image_input_name=None,
    )
    assert payload["node_image"]["inputs"]["path"] is None


@pytest.mark.parametrize("workflow_name", ["test_wf", "nonexistent"])
def test_build_multiple_workflows(mock_cfg, base_api, workflow_name):
    """Check that the builder uses the correct config based on the name."""
    builder = PromptBuilder(cfg=mock_cfg)
    payload = builder.build(
        wf_api=deepcopy(base_api),
        workflow_name=workflow_name,
        base_prompt="Parametrized",
    )
    if workflow_name == "test_wf":
        assert payload["node_prompt"]["inputs"]["text"] == "Parametrized"
    else:
        # Should be unchanged
        assert payload == base_api
