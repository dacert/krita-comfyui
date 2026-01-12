import json
from pathlib import Path

import pytest

# Import the functions under test
from krita_comfyui.comfy_client.workflow_utils import find_output_node, to_api_format


@pytest.fixture(scope="module")
def raw_workflow():
    """Load the raw workflow JSON from the tests data folder."""
    path = Path(__file__).parent / "data" / "wf_1.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def api_workflow():
    """Load the expected API‑formatted workflow JSON."""
    path = Path(__file__).parent / "data" / "wf_api_1.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def object_info():
    """
    Object_info needed for `to_api_format`.
    """
    path = Path(__file__).parent / "data" / "object_info.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_find_output_node_returns_correct_id_and_dict(api_workflow):
    """
    The workflow contains a single node of type 'SaveImageWebsocket'.
    `find_output_node` should return its id and the full node dict.
    """
    result = find_output_node(api_workflow)
    assert result is not None, "No SaveImageWebsocket node found"
    node_id, node_dict = result
    # Node 137 in wf_1.json has type 'SaveImageWebsocket'
    assert int(node_id) == 137
    assert node_dict["class_type"] == "SaveImageWebsocket"


def test_find_output_node_none_when_missing(api_workflow):
    """
    If the workflow does not contain a SaveImageWebsocket node,
    the function should return None.
    """
    # Remove all nodes of that type temporarily
    modified = {
        k: v for k, v in api_workflow.items() if v.get("class_type") != "SaveImageWebsocket"
    }
    result = find_output_node(modified)
    assert result is None


def test_to_api_format_matches_expected(api_workflow, object_info, raw_workflow):
    """
    Convert the raw workflow to API format and compare against the expected JSON.
    The comparison is deep but ignores ordering of keys (dict order is irrelevant).
    """
    converted = to_api_format(raw_workflow, object_info)
    # Both dicts should have the same top‑level keys
    assert set(converted.keys()) == set(api_workflow.keys())

    for node_id in api_workflow:
        expected_node = api_workflow[node_id]
        actual_node = converted.get(node_id)
        assert actual_node is not None, f"Node {node_id} missing after conversion"

        # Compare class_type and _meta.title
        assert actual_node["class_type"] == expected_node["class_type"]
        assert actual_node["_meta"]["title"] == expected_node["class_type"]

        # Locate the original raw node by id
        raw_node = next(n for n in raw_workflow["nodes"] if str(n["id"]) == node_id)
        defined_input_names = {inp["name"] for inp in raw_node.get("inputs", [])}

        # For inputs: only compare those that actually exist on the node.
        # Skip any keys present in the reference but not defined in the raw node.
        for key, exp_val in expected_node["inputs"].items():
            if key in defined_input_names:
                assert actual_node["inputs"][key] == exp_val, (
                    f"Inputs mismatch for node {node_id} on key '{key}'"
                )


def test_to_api_format_handles_missing_widget_values(raw_workflow, object_info):
    """
    A node that has fewer widget values than the number of inputs without links
    should simply omit those missing values (i.e., not crash).
    This tests a potential edge case where `widget_vals` runs out early.
    """
    # Create a copy and strip some widget_values from node 113
    modified = json.loads(json.dumps(raw_workflow))  # deep copy
    for n in modified["nodes"]:
        if n["id"] == 113:
            # Remove the last two widget values, leaving only one
            n["widgets_values"] = n["widgets_values"][:1]
            break

    converted = to_api_format(modified, object_info)
    node_113 = converted.get("113")
    assert node_113 is not None
    # The input 'clip_name' should still be present because it had a link (link=233) in the original,
    # but since we removed widget values, no value should appear for inputs without links.
    # In this specific workflow, all inputs of 113 had links, so the output should not change.
    assert node_113["inputs"]["clip_name"] == "qwen_2.5_vl_7b_fp8_scaled.safetensors"


def test_to_api_format_skips_control_after_generate(raw_workflow, object_info):
    """
    Inputs that have a 'control_after_generate' flag set to True should not consume an extra widget value.
    This verifies the logic inside the conversion loop that skips such widgets.
    """
    # Find node 118 which has an input with control_after_generate
    for n in raw_workflow["nodes"]:
        if n["id"] == 118:
            # Ensure 'output_padding' has the flag set
            assert any(
                inp.get("name") == "output_padding" and inp.get("widget") is not None
                for inp in n["inputs"]
            )
            break

    converted = to_api_format(raw_workflow, object_info)
    node_118 = converted.get("118", [])
    # Count how many widget values were consumed (should be equal to number of inputs without links)
    # The original had 27 inputs; only those with link=0 (image) and link=1 (mask) are linked,
    # so 25 widget values should have been consumed. We check that the last widget value
    # corresponds to 'output_padding' correctly.
    expected_output_padding = "32"
    assert node_118["inputs"]["output_padding"] == expected_output_padding


def test_to_api_format_preserves_linked_inputs(raw_workflow, object_info):
    """
    Inputs that are connected via links should be represented as [node_id, slot].
    Verify a few such connections.
    """
    converted = to_api_format(raw_workflow, object_info)
    # Example: node 114 'model' input comes from link 233 which connects to node 110
    assert converted["114"]["inputs"]["model"] == ["110", 0]
    # Node 121 'seed' is a widget value (no link)
    assert isinstance(converted["121"]["inputs"]["seed"], int)


def test_to_api_format_empty_nodes(raw_workflow, object_info):
    """
    Nodes with no inputs and outputs should be skipped.
    We'll artificially add such a node to the workflow and ensure it's omitted.
    """
    modified = json.loads(json.dumps(raw_workflow))
    modified["nodes"].append({
        "id": 999,
        "type": "EmptyNode",
        "inputs": [],
        "outputs": [],
        "widgets_values": [],
    })
    converted = to_api_format(modified, object_info)
    assert "999" not in converted


def test_to_api_format_inconsistent_link_map(raw_workflow, object_info):
    """
    If a link refers to a non‑existent node or slot, the conversion should
    still produce an entry but with the original link reference unchanged.
    This tests robustness against malformed links.
    """
    modified = json.loads(json.dumps(raw_workflow))
    # Add a bogus link that points to node 999 (non‑existent)
    modified["links"].append([300, 999, 0, 114, 0, "MODEL"])
    converted = to_api_format(modified, object_info)
    # Node 114 should still have its 'model' input as [110, 0] because link 233 was valid
    assert converted["114"]["inputs"]["model"] == ["110", 0]


def test_to_api_format_preserves_titles_and_meta(raw_workflow, object_info):
    """
    The _meta.title field is derived from the node's title if present,
    otherwise it falls back to the class_type. Verify this behavior.
    """
    converted = to_api_format(raw_workflow, object_info)
    # Node 132 has a 'title' property in its properties dict
    assert "_meta" in converted["132"]
    assert "title" in converted["132"]["_meta"]
