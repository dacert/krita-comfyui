import random
from typing import Any, Dict

class PromptBuilder:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def build(
        self,
        wf_api: Dict[str, Any],
        workflow_name: str,
        base_prompt: str,
        seed: int | None = None
    ) -> dict:
        """
        Builds the JSON payload to send to ComfyUI.

        Parameters
        ----------
        wf_api : dict
            The raw workflow API dictionary (already parsed from a .json file).
        workflow_name : str
            Name of the workflow that should be used.
        base_prompt : str
            Text prompt to inject into the workflow.
        seed : int | None, optional
            Seed value. If ``None`` a random one is generated.

        Returns
        -------
        dict
            workflow ready for the ComfyUI endpoint.
        """
        # Find the workflow definition in the config
        workflows = self.cfg.get("workflows", [])
        wf_cfg = next((w for w in workflows if w["workflow_name"] == workflow_name), None)
        if wf_cfg is None:
            # No specific configuration – return the original payload unchanged.
            return wf_api

        # Copy the API dict to avoid mutating the caller's data
        payload = {k: v.copy() for k, v in wf_api.items()}

        # Inject prompt and seed values using node mapping from config
        inputs_map = wf_cfg["inputs"]

        prompt_node_id = inputs_map["prompt"]["node_id"]
        prompt_prop    = inputs_map["prompt"]["property"]
        payload[prompt_node_id]["inputs"][prompt_prop] = base_prompt

        seed_val = seed if seed is not None else random.randint(1, 11768320141)
        seed_node_id = inputs_map["seed"]["node_id"]
        seed_prop    = inputs_map["seed"]["property"]
        payload[seed_node_id]["inputs"][seed_prop] = seed_val

        # Return JSON string
        return payload