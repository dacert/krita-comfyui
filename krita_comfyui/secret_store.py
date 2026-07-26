import base64
import json
import os
import stat
from pathlib import Path

SECRETS_DIR = Path.home() / ".krita_comfyui"
SECRETS_FILE = SECRETS_DIR / "secrets.json"


def _ensure_dir():
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            SECRETS_DIR.chmod(stat.S_IRWXU)
        except OSError:
            pass


def _read_secrets() -> dict[str, str]:
    if not SECRETS_FILE.exists():
        return {}
    try:
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        else:
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def _write_secrets(data: dict[str, str]):
    _ensure_dir()
    SECRETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if os.name == "posix":
        try:
            SECRETS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def store(key: str, value: str):
    secrets = _read_secrets()
    secrets[key] = base64.b64encode(value.encode()).decode()
    _write_secrets(secrets)


def retrieve(key: str) -> str | None:
    secrets = _read_secrets()
    encoded = secrets.get(key)
    if encoded is None:
        return None
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return None


def delete(key: str):
    secrets = _read_secrets()
    secrets.pop(key, None)
    _write_secrets(secrets)


def has_secrets_file() -> bool:
    return SECRETS_FILE.exists()
