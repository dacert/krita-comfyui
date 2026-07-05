"""
Utility functions for converting raw workflows and searching nodes.
"""


def find_output_node(api_data: dict):
    """
    Find the first node with class_type == 'SaveImageWebsocket'.
    Returns (node_id, node_dict) or None if not found.
    """
    for node_id, node in api_data.items():
        if isinstance(node, dict) and node.get("class_type") == "SaveImageWebsocket":
            return node_id, node
    return None
