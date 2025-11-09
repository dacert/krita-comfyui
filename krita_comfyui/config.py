"""
Typed configuration model and persistence helpers.
"""

import json
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field
from .config_logging import getLogger

DEFAULT_URL = "http://localhost:8188"


@dataclass
class WorkflowInput:
    node_id: str
    property: str | None = None


@dataclass
class WorkflowConfig:
    workflow_name: str
    inputs: Dict[str, WorkflowInput] = field(default_factory=dict)


@dataclass
class Config:
    comfyui_url: str
    workflows: List[WorkflowConfig] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Load configuration from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        # Convert raw dicts into the dataclass hierarchy
        workflows = [
            WorkflowConfig(
                workflow_name=wf["workflow_name"],
                inputs={
                    k: WorkflowInput(**v)
                    for k, v in wf.get("inputs", {}).items()
                },
            )
            for wf in data.get("workflows", [])
        ]
        return cls(comfyui_url=data["comfyui_url"], workflows=workflows)

    def save(self, path: Path):
        """Persist configuration to disk."""
        # Serialise dataclasses back into plain dicts
        serialised = {
            "comfyui_url": self.comfyui_url,
            "workflows": [
                {
                    "workflow_name": wf.workflow_name,
                    "inputs": {
                        k: {"node_id": v.node_id, "property": v.property}
                        for k, v in wf.inputs.items()
                    },
                }
                for wf in self.workflows
            ],
        }
        path.write_text(json.dumps(serialised, indent=2), encoding="utf-8")

    @classmethod
    def load_or_create(cls, path: Path) -> "Config":
        """
        Load configuration from *path*.
        If the file does not exist or cannot be parsed,
        create a **default** configuration, write it to disk,
        and return that instance.

        Returns
        -------
        Config
            The loaded or newly‑created configuration.
        """
        logger = getLogger("config")

        if path.exists():
            try:
                return cls.load(path)
            except Exception as e:
                logger.warning(
                    f"Failed to load config at {path}: {e}"
                )

        default_cfg = cls(
            comfyui_url=DEFAULT_URL,
            workflows=[],
        )
        try:
            default_cfg.save(path)
            logger.info(f"Created default config at {path}")
        except Exception as e:
            logger.error(
                f"Could not write default config to {path}: {e}"
            )
        return default_cfg