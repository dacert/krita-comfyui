import json
from .workflow_utils import to_api_format
from urllib.parse import urlencode
import urllib.request
from urllib.parse import quote


class ComfyHttpClient:
    """
    HTTP Client for interacting with the ComfyUI server (HTTP API).
    """
    TIMEOUT_SECONDS = 5

    def __init__(self, server: str = "http://127.0.0.1:8188"):
        self.server_address = server.rstrip("/")
        self._object_info_cache: dict | None = None

    def get_workflows_list(self) -> dict:
        query = {
            "dir": "workflows", "recurse": True,
            "split": False, "full_info": True
        }
        url = f"{self.server_address}/api/userdata?{urlencode(query)}"
        return self._fetch_json(url)

    def get_workflow(self, name: str) -> dict:
        url = f"{self.server_address}/api/userdata/workflows%2F{quote(name)}"
        return self._fetch_json(url)

    def get_object_info(self) -> dict:
        if self._object_info_cache is not None:
            return self._object_info_cache

        url = f"{self.server_address}/api/object_info"
        data = self._fetch_json(url)

        self._object_info_cache = data
        return data

    def get_workflow_api(self, name: str) -> dict:
        raw = self.get_workflow(name)
        object_info = self.get_object_info()
        return to_api_format(raw, object_info)

    def queue_prompt(self, prompt: dict, client_id: str) -> dict:
        payload = {"prompt": prompt, "client_id": client_id}
        url = f"{self.server_address}/prompt"
        return self._post_json(url, payload)

    def get_settings(self) -> dict:
        url = f"{self.server_address}/api/settings"
        return self._fetch_json(url, 2)

    def _fetch_json(self, url: str, timeout: float = TIMEOUT_SECONDS) -> dict:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())

    def _post_json(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
