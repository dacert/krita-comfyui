import json
from .workflow_utils import to_api_format
import urllib.parse
import urllib.request
from urllib.parse import quote

class ComfyUIHttpClient:
    """
    Http Cliente para interactuar con el servidor ComfyUI (HTTP API).
    """

    def __init__(self, server: str = "http://127.0.0.1:8188"):
        self.server_address = server.rstrip("/")

    def get_workflows_list(self) -> dict:
        query = urllib.parse.urlencode(
            {"dir": "workflows", "recurse": True, "split": False, "full_info": True}
        )
        url = f"{self.server_address}/api/userdata?{query}"
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read())
    
 
    def get_workflow(self, name: str) -> dict:
        url = f"{self.server_address}/api/userdata/workflows%2F{quote(name)}"
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read())
    

    def get_object_info(self) -> dict:
        url = f"{self.server_address}/api/object_info"
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read())    

    def get_workflow_api(self, name: str) -> dict:
        raw = self.get_workflow(name)
        object_info = self.get_object_info()
        return to_api_format(raw, object_info)

    def queue_prompt(self, prompt: dict, client_id: str) -> dict:
        payload = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.server_address}/prompt", data=data
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        query = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": folder_type}
        )
        url = f"{self.server_address}/view?{query}"
        with urllib.request.urlopen(url) as resp:
            return resp.read()
