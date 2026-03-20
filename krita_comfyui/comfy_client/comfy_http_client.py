import json
import urllib.request
import uuid
from urllib.parse import quote, urlencode, urljoin

from .workflow_utils import to_api_format


class ComfyHttpClient:
    """
    HTTP Client for interacting with the ComfyUI server (HTTP API).
    """

    TIMEOUT_SECONDS = 5

    def __init__(self, server: str = "http://127.0.0.1:8188"):
        self.server_address = server.rstrip("/")
        self._object_info_cache: dict | None = None

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def upload_file(
        self,
        path: str,
        file_name: str,
        file_bytes,
        subfolder: str = "",
        ref: str = "",
        ref_subfolder: str = "",
        overwrite: bool = False,
    ) -> dict | None:
        """
        Upload a single image to the ComfyUI server.

        Parameters
        ----------
        path : str
            Target folder inside the upload endpoint (e.g. ``images``).
        file_name : str
            Name of the file being uploaded.
        file_bytes : bytes
            Raw binary data of the file.
        subfolder : str, optional
            Optional sub‑folder under *path* where the file should be stored.
        ref : str, optional
            Reference image filename (if any).
        ref_subfolder : str, optional
            Sub‑folder for the reference image.
        overwrite : bool, default False
            Whether to overwrite an existing file with the same name.

        Returns
        -------
        dict | None
            Server response parsed as JSON or ``None`` if parsing failed.
        """
        fields: dict[str, str | dict] = {"type": "input"}

        if ref:
            fields["original_ref"] = {
                "filename": ref,
                "subfolder": ref_subfolder,
                "type": "input",
            }

        if overwrite:
            fields["overwrite"] = "true"

        if subfolder:
            fields["subfolder"] = subfolder

        body, content_type = self._encode_multipart_formdata(
            fields=fields, files=[("image", file_name, file_bytes)]
        )

        url = urljoin(f"{self.server_address}/", f"upload/{path}")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": content_type},
        )
        with urllib.request.urlopen(req) as resp:
            resp_data = json.loads(resp.read().decode())

        if isinstance(resp_data, dict):
            return resp_data
        return None

    def get_workflows_list(self) -> dict:
        query = {
            "dir": "workflows",
            "recurse": True,
            "split": False,
            "full_info": True,
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
        # Pass the timeout explicitly – makes the intent clear
        return self._fetch_json(url, timeout=2)

    # --------------------------------------------------------------------- #
    # Internals
    # --------------------------------------------------------------------- #

    def _fetch_json(self, url: str, timeout: float = TIMEOUT_SECONDS) -> dict:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())

    def _post_json(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _encode_multipart_formdata(
        self,
        fields: dict[str, str | dict],
        files: list[tuple[str, str, bytes]],
    ) -> tuple[bytes, str]:
        """
        Construct a multipart/form-data body.

        Parameters
        ----------
        fields : dict of form field name → value
            Textual fields to include in the payload.
        files : list of tuples (field_name, filename, file_bytes)
            Binary data to upload.

        Returns
        -------
        tuple[bytes, str]
            The raw request body and a ``Content-Type`` header value.
        """
        boundary = uuid.uuid4().hex
        lines: list[str] = []

        # Add form fields (text only)
        for key, value in fields.items():
            lines.append(f"--{boundary}")
            lines.append(f'Content-Disposition: form-data; name="{key}"')
            lines.append("")
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            lines.append(value_str)

        # Add file parts (binary)
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

        # Final boundary
        lines.append(f"--{boundary}--")
        lines.append("")
        body = "\r\n".join(lines).encode("latin1")
        content_type = f"multipart/form-data; boundary={boundary}"
        return body, content_type
