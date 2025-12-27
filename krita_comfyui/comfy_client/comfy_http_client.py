import json
import uuid
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

    def upload_file(
        self,
        path: str,
        file_name: str,
        file_bytes,
        subfolder: str = "",
        ref: str = "",
        ref_subfolder: str = "",
        overwrite: bool = False,
    ) -> str | None:
        fields = {"type": "input"}
        if ref:
            fields["original_ref"] = {"filename": ref, "subfolder": ref_subfolder, "type": "input"}
        if overwrite:
            fields["overwrite"] = "true"
        if subfolder:
            fields["subfolder"] = subfolder

        body, content_type = self._encode_multipart_formdata(
            fields=fields,
            files=[("image", file_name, file_bytes)],
        )

        req = urllib.request.Request(
            f"{self.server_address}/upload/{path}",
            data=body,
            headers={"Content-Type": content_type},
        )
        with urllib.request.urlopen(req) as resp:
            resp_data = json.loads(resp.read().decode())

        # The server returns a JSON object on success
        if isinstance(resp_data, dict):
            return resp_data
        return None

    def get_workflows_list(self) -> dict:
        query = {"dir": "workflows", "recurse": True, "split": False, "full_info": True}
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

    def _encode_multipart_formdata(self, fields, files):
        """
        Construct a multipart/form-data body.

        :param fields: dict of form field name -> value
        :param files: list of tuples (field_name, filename, file_bytes)
        :return: (body_bytes, content_type_header)
        """
        boundary = uuid.uuid4().hex
        lines = []

        for key, value in fields.items():
            lines.append(f"--{boundary}")
            lines.append(f'Content-Disposition: form-data; name="{key}"')
            lines.append("")
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            lines.append(value_str)

        for field_name, filename, file_bytes in files:
            lines.append(f"--{boundary}")
            lines.append(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'
            )
            lines.append("Content-Type: application/octet-stream")
            lines.append("")
            if not isinstance(file_bytes, (bytes, bytearray)):
                file_bytes = bytes(file_bytes)
            lines.append(file_bytes.decode("latin1"))  # binary data

        lines.append(f"--{boundary}--")
        lines.append("")
        body = "\r\n".join(lines).encode("latin1")
        content_type = f"multipart/form-data; boundary={boundary}"
        return body, content_type
