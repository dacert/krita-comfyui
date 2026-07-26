"""
Typed configuration model and persistence helpers.
"""

import json
import os
import stat
from dataclasses import dataclass, field
from dataclasses import fields as _dc_fields
from pathlib import Path
from typing import Any

from . import secret_store
from .config_logging import getLogger

DEFAULT_URL = "http://localhost:8000"
HOME_CONFIG_FILE = secret_store.SECRETS_DIR / "config.json"
LEGACY_CONFIG_NAME = "krita_comfyui.config"


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


def find_or_migrate_config(plugin_dir: str | os.PathLike[str]) -> Path:
    logger = getLogger("config")
    home_cfg = HOME_CONFIG_FILE
    if home_cfg.exists():
        return home_cfg

    legacy_cfg = Path(plugin_dir) / LEGACY_CONFIG_NAME
    if legacy_cfg.exists():
        try:
            secret_store._ensure_dir()
            home_cfg.write_bytes(legacy_cfg.read_bytes())
            if os.name == "posix":
                home_cfg.chmod(stat.S_IRUSR | stat.S_IWUSR)
            legacy_cfg.unlink()
            logger.info("Migrated config from %s to %s", legacy_cfg, home_cfg)
        except OSError as exc:
            logger.warning("Failed to migrate config from %s to %s: %s", legacy_cfg, home_cfg, exc)

    return home_cfg


@dataclass
class WorkflowInput:
    node_id: str
    property: str | None = None


@dataclass
class WorkflowConfig:
    workflow_name: str
    inputs: dict[str, WorkflowInput] = field(default_factory=dict)

    def has_image_loader(self) -> bool:
        inputs_map = self.inputs
        image_input = inputs_map.get("image_loader")
        return bool(image_input and image_input.node_id)


@dataclass
class Config:
    logger: bool
    comfyui_url: str
    api_key: str = ""
    workflows: list[WorkflowConfig] = field(default_factory=list)
    timeout_minutes: int = 5
    clipspace_enabled: bool = True

    def get_workflow(self, workflow_name: str) -> WorkflowConfig | None:
        return next((w for w in self.workflows if w.workflow_name == workflow_name), None)

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
        timeout_minutes = data.get("timeout_minutes", 5)
        timeout_minutes = max(1, min(60, int(timeout_minutes)))
        api_key = data.get("api_key", "")
        env_key = os.environ.get("KRITA_COMFYUI_API_KEY")
        if env_key:
            api_key = env_key
        else:
            stored_key = secret_store.retrieve("api_key")
            if stored_key:
                api_key = stored_key
            elif api_key:
                secret_store.store("api_key", api_key)
                data["api_key"] = ""
                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return cls(
            logger=data.get("logger", False),
            comfyui_url=data.get("comfyui_url", DEFAULT_URL),
            api_key=api_key,
            workflows=workflows,
            timeout_minutes=timeout_minutes,
            clipspace_enabled=data.get("clipspace_enabled", True),
        )

    def save(self, path: Path):
        """Persist configuration to disk."""
        if self.api_key:
            secret_store.store("api_key", self.api_key)
        else:
            secret_store.delete("api_key")
        serialised = {
            "logger": self.logger,
            "comfyui_url": self.comfyui_url,
            "api_key": "",
            "timeout_minutes": self.timeout_minutes,
            "clipspace_enabled": self.clipspace_enabled,
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
            api_key="",
            workflows=[],
        )
        try:
            default_cfg.save(path)
            logger.debug(f"Created default config at {path}")
        except Exception as e:
            logger.error(f"Could not write default config to {path}: {e}")
        return default_cfg
