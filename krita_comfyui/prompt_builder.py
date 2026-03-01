"""
Builds the JSON payload to send to Comfy.
"""

import copy
import random
from typing import Any, Dict

from .config import Config


class PromptBuilder:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def build(
        self,
        wf_api: Dict[str, Any],
        workflow_name: str,
        base_prompt: str,
        image_input_name: str | None = None,
        seed: int | None = None,
    ) -> dict:
        """
        Modifies `wf_api` with the user prompt and optional seed.
        Returns a **new** dictionary (original untouched).
        """

        # Find the workflow definition in the config
        wf_cfg = next((w for w in self.cfg.workflows if w.workflow_name == workflow_name), None)
        if wf_cfg is None:
            # No specific configuration → return the original payload unchanged.
            return wf_api

        # Deep‑copy the API dict to avoid mutating the caller's data
        payload = copy.deepcopy(wf_api)

        # Inject prompt and seed values using node mapping from config
        inputs_map = wf_cfg.inputs

        prompt_input = inputs_map["prompt"]
        payload[prompt_input.node_id]["inputs"][prompt_input.property] = base_prompt

        seed_val = seed if seed is not None else random.randint(1, 11768320141)
        seed_input = inputs_map["seed"]
        payload[seed_input.node_id]["inputs"][seed_input.property] = seed_val

        # Handle optional image input
        image_input = inputs_map.get("image_loader")
        if image_input_name and image_input.node_id:
            payload[image_input.node_id]["inputs"][image_input.property] = image_input_name

        return payload
