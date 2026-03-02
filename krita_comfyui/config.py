"""
Typed configuration model and persistence helpers.
"""

import json
from dataclasses import dataclass, field
from dataclasses import fields as _dc_fields
from pathlib import Path
from typing import Any

from .config_logging import getLogger

DEFAULT_URL = "http://localhost:8188"


def _filter_input_dict(raw: dict[str, Any], cls):
    """
    Return a new dict containing only the keys that belong to ``cls``.

    Parameters
    ----------
    raw : dict
        Raw dictionary read from JSON.
    cls : type
        The dataclass whose field names should be preserved.

    Returns
    -------
    dict
        Filtered dictionary with only valid fields for ``cls``.
    """
    allowed = {f.name for f in _dc_fields(cls)}
    return {k: raw[k] for k in allowed if k in raw}


@dataclass
class WorkflowInput:
    node_id: str
    property: str | None = None


@dataclass
class WorkflowConfig:
    workflow_name: str
    inputs: dict[str, WorkflowInput] = field(default_factory=dict)


@dataclass
class Config:
    logger: bool
    comfyui_url: str
    workflows: list[WorkflowConfig] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Load configuration from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        # Convert raw dicts into the dataclass hierarchy
        workflows = [
            WorkflowConfig(
                workflow_name=wf["workflow_name"],
                inputs={
                    k: WorkflowInput(**_filter_input_dict(v, WorkflowInput))
                    for k, v in wf.get("inputs", {}).items()
                },
            )
            for wf in data.get("workflows", [])
        ]
        return cls(
            logger=data.get("logger", False),
            comfyui_url=data.get("comfyui_url", DEFAULT_URL),
            workflows=workflows,
        )

    def save(self, path: Path):
        """Persist configuration to disk."""
        # Serialise dataclasses back into plain dicts
        serialised = {
            "logger": self.logger,
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
                logger.error(f"Failed to load config at {path}: {e}")

        default_cfg = cls(
            logger=False,
            comfyui_url=DEFAULT_URL,
            workflows=[],
        )
        try:
            default_cfg.save(path)
            logger.debug(f"Created default config at {path}")
        except Exception as e:
            logger.error(f"Could not write default config to {path}: {e}")
        return default_cfg
