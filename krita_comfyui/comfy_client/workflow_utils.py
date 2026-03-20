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
        if isinstance(node, dict) and node.get("class_type") == "SaveImageWebsocket":
            return node_id, node
    return None


def api_nodes(workflow: dict, object_info: dict, subgraph_defs: dict, current_node: dict | None):
    link_map = {}
    for link in workflow["links"]:
        if isinstance(link, list):
            link_id, src_node, src_slot, _, _, _ = link
        else:
            link_id = link["id"]
            src_node = link["origin_id"]
            src_slot = link["origin_slot"]

        link_map[link_id] = (src_node, src_slot)

    current_node_widgets = {}
    if current_node:
        current_node_inputs = [i for i in current_node["inputs"] if i.get("widget")]
        for i, val in enumerate(current_node["widgets_values"]):
            current_node_widgets[current_node_inputs[i]["name"]] = val

    nodes: dict[str, Any] = {}

    # Sort numeric IDs first to avoid int/str comparison issues
    def sort_key(item):
        try:
            return (0, int(item["id"]))
        except (ValueError, TypeError):
            return (1, item["id"])

    workflow_nodes = sorted(workflow["nodes"], key=sort_key)
    for n in workflow_nodes:
        if n.get("mode", 0) != 0:  # bypass node
            continue

        if len(n["inputs"]) == 0 and len(n["outputs"]) == 0:
            continue

        node_id = str(n["id"])
        node_type = n["type"]
        title = n.get("title", None)
        display_name = None

        inputs_info = {}
        type_info = object_info.get(node_type, None)
        if type_info is not None:
            info = type_info["input"]
            inputs_info = info.get("required", {}) | info.get("optional", {})
            display_name = type_info.get("display_name", None)

        if not title and display_name:
            title = display_name
        elif not (title and display_name):
            title = node_type

        if node_type in subgraph_defs:
            sub_workflow = subgraph_defs[node_type]
            for i, out in enumerate(sub_workflow.get("outputs", [])):
                link_id = out["linkIds"][0]
                for link in sub_workflow.get("links", []):
                    if link_id == link["id"]:
                        origin_id, origin_slot = link["origin_id"], link["origin_slot"]
                        n_output = n.get("outputs", [])
                        if len(n_output) > i:
                            for output_link in n.get("outputs", [])[i]["links"]:
                                link_map[output_link] = [f"{node_id}:{origin_id}", origin_slot]
                        break

            sub_nodes = api_nodes(sub_workflow, object_info, subgraph_defs, n)
            for key in sub_nodes:
                sub_node = sub_nodes[key]
                for k in sub_node["inputs"]:
                    if isinstance(sub_node["inputs"][k], list):
                        src, link = sub_node["inputs"][k]
                        if "-10" in src:
                            new_src = link_map[link][0]
                            new_slot = link_map[link][1]
                            sub_node["inputs"][k] = [str(new_src), new_slot]
                nodes[key] = sub_node

            continue

        widget_vals = n.get("widgets_values", [])
        widget_index = 0

        widgets = {}
        widget_inputs = [i for i in n.get("inputs", []) if i.get("widget")]
        for widget_input in widget_inputs:
            inp_info = inputs_info.get(widget_input["name"], [])
            if widget_index < len(widget_vals):
                widgets[widget_input["name"]] = widget_vals[widget_index]
                widget_index += 1

            # Skip control_after_generate (optional UI behaviour)
            if len(inp_info) > 1 and inp_info[1].get("control_after_generate", False):
                widget_index += 1

        widget_index = 0
        inputs: dict[str, Any] = {}

        if current_node and current_node["type"] in subgraph_defs:
            for inp in n.get("inputs", []):
                link_id = inp.get("link")
                name = inp.get("name")

                if link_id is None:
                    # No link – use the widget value
                    if name in widgets:
                        inputs[inp["name"]] = widgets[name]
                else:
                    src_node, src_slot = link_map[link_id]
                    if src_node == -10:
                        external_link = current_node["inputs"][src_slot]["link"]
                        input_name = current_node["inputs"][src_slot]["name"]
                        if not external_link:
                            if input_name in current_node_widgets:
                                inputs[inp["name"]] = current_node_widgets[input_name]
                            elif name in widgets:
                                inputs[inp["name"]] = widgets[name]
                        else:
                            inputs[inp["name"]] = [
                                f"{current_node['id']}:{src_node!s}",
                                external_link,
                            ]
                    else:
                        inputs[inp["name"]] = [f"{current_node['id']}:{src_node!s}", src_slot]

            node_entry: dict[str, Any] = {
                "inputs": inputs,
                "class_type": node_type,
                "_meta": {"title": title},
            }

            nodes[f"{current_node['id']}:{node_id}"] = node_entry
        else:
            for inp in n.get("inputs", []):
                link_id = inp.get("link")
                name = inp.get("name")

                if link_id is None:
                    # No link – use the widget value
                    if name in widgets:
                        inputs[inp["name"]] = widgets[name]
                else:
                    src_node, src_slot = link_map[link_id]
                    inputs[inp["name"]] = [str(src_node), src_slot]

            node_entry: dict[str, Any] = {
                "inputs": inputs,
                "class_type": node_type,
                "_meta": {"title": title},
            }

            nodes[node_id] = node_entry

    return nodes


def to_api_format(workflow: dict, object_info: dict) -> dict:
    """
    Convert a raw ComfyUI workflow (JSON from `/api/userdata`) into the
    simplified API format used by the plugin.
    """
    # workflow = flatten_subgraphs(workflow)
    subgraph_defs = {g["id"]: g for g in workflow.get("definitions", {}).get("subgraphs", [])}

    return api_nodes(workflow, object_info, subgraph_defs, None)
