"""
Utility functions for converting raw workflows and searching nodes.
"""

from typing import Any


def find_output_node(api_data: dict):
    """
    Find the first node with class_type == 'SaveImageWebsocket'.
    Returns (node_id, node_dict) or None if not found.
    """
    for node_id, node in api_data.items():
        if (isinstance(node, dict) and
                node.get("class_type") == "SaveImageWebsocket"):
            return node_id, node
    return None


def to_api_format(workflow: str, object_info: dict) -> dict:
    """
    Convert a raw ComfyUI workflow (JSON from `/api/userdata`) into the
    simplified API format used by the plugin.
    """
    link_map = {}
    for link in workflow["links"]:
        link_id, src_node, src_slot, _, _, _ = link
        link_map[link_id] = (src_node, src_slot)

    nodes: dict[str, Any] = {}

    # Sort numeric IDs first to avoid int/str comparison issues
    def sort_key(item):
        try:
            return (0, int(item["id"]))
        except (ValueError, TypeError):
            return (1, item["id"])

    workflow_nodes = sorted(workflow["nodes"], key=sort_key)

    for n in workflow_nodes:
        node_id = str(n["id"])
        node_type = n["type"]

        if len(n["inputs"]) == 0 and len(n["outputs"]) == 0:
            continue

        inputs_info = {}
        type_info = object_info.get(node_type, None)
        if type_info is not None:
            info = type_info["input"]
            inputs_info = info.get("required", {}) | info.get("optional", {})

        widget_vals = n.get("widgets_values", [])
        widget_index = 0

        inputs: dict[str, Any] = {}
        for inp in n.get("inputs", []):
            link_id = inp.get("link")
            widget = inp.get("widget")
            if link_id is None:
                # No link – use the widget value
                if widget is not None and widget_index < len(widget_vals):
                    val = widget_vals[widget_index]
                    inputs[inp["name"]] = val
                    widget_index += 1
            else:
                src_node, src_slot = link_map[link_id]
                inputs[inp["name"]] = [str(src_node), src_slot]
                widget = inp.get("widget")
                if widget is not None:
                    widget_index += 1

            # Skip control_after_generate (optional UI behaviour)
            inp_info = inputs_info.get(inp["name"], [])
            if (len(inp_info) > 1 and
                    inp_info[1].get("control_after_generate", False)):
                widget_index += 1

        node_entry: dict[str, Any] = {
            "inputs": inputs,
            "class_type": node_type,
            "_meta": {"title": n.get("title", node_type)},
        }

        nodes[node_id] = node_entry

    return nodes
