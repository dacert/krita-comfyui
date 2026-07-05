import asyncio
import json
import uuid
from collections.abc import Callable
from logging import Logger
from typing import Any
from urllib.parse import urlparse

from PyQt5.QtGui import QImage

from ..websockets.src.websockets import ClientConnection
from ..websockets.src.websockets import connect as websockets_connect
from ..websockets.src.websockets.exceptions import ConnectionClosedOK
from .comfy_http_client import ComfyHttpClient
from .image_prompt import ImagePrompt
from .image_utils import (
    create_transparent_argb32_image,
    fix_image,
    qimage_to_bytes,
    reduce_alpha_by_selection,
)


class ComfyExecutionError(Exception):
    """Raised when Comfy returns 'ExecutionError' during workflow execution."""


class ComfyClient:
    """
    Asynchronous client to interact with the ComfyUI server (WS).
    """

    def __init__(self, logger: Logger, server: str, api_key: str = ""):
        self.logger = logger
        self.server_address = self.get_ws_host(server)
        self.api_key = api_key
        self.http_client = ComfyHttpClient(server, api_key)
        self.client_id = str(uuid.uuid4())
        self.ws: ClientConnection

    async def __aenter__(self):
        await self._connect_ws()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    def get_ws_host(self, url: str) -> str | None:
        parsed = urlparse(url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        if parsed.port:
            return f"{scheme}://{parsed.hostname}:{parsed.port}"
        return f"{scheme}://{parsed.hostname}"

    async def _connect_ws(self) -> None:
        url = f"{self.server_address}/ws?clientId={self.client_id}"
        if self.api_key:
            url += f"&token={self.api_key}"
        self.ws = await websockets_connect(url, max_size=2**30, ping_timeout=60)
        self.logger.debug(f"[ComfyClient]  WS connected as {self.client_id}")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self.ws:
            await self.ws.close()
            self.logger.debug("[ComfyClient] WS closed")

    async def _receive_images(
        self,
        prompt_id: str,
        num_nodes: int,
        output_node: str,
        *,
        timeout: float | None = None,
        progress_callback: Callable[[float], Any] | None = None,
    ) -> dict[str, list[bytes]]:
        """
        Receive images from the server for a given prompt.
        """
        output_images: dict[str, list[bytes]] = {}
        current_node: str | None = None
        cache_nodes = 0

        async def _recv():
            nonlocal current_node, cache_nodes
            try:
                async for message in self.ws:
                    if isinstance(message, str):
                        msg = json.loads(message)

                        if msg.get("type") == "executing":
                            data = msg["data"]
                            if data["prompt_id"] == prompt_id:
                                if data["node"] is None:
                                    break  # Execution is done
                                else:
                                    current_node = data["node"]

                        elif msg.get("type") == "execution_success":
                            data = msg["data"]
                            if data["prompt_id"] == prompt_id:
                                break  # Execution is done

                        elif msg.get("type") == "execution_error":
                            data = msg["data"]
                            error_message = data["exception_message"]
                            self.logger.error(f"[ComfyClient] ComfyError: {error_message}")
                            raise ComfyExecutionError(error_message)

                        elif msg.get("type") == "notification":
                            data = msg["data"]
                            self.logger.info(f"[ComfyClient] Comfy Notification: {data}")

                        elif msg["type"] == "execution_cached":
                            cache_nodes = len(msg["data"]["nodes"])

                        elif msg["type"] == "progress_state":
                            nodes = msg["data"]["nodes"]
                            finished_nodes = sum(
                                1 for n in nodes.values() if n.get("state") == "finished"
                            )
                            running_progress = sum(
                                n["value"] / n["max"]
                                for n in nodes.values()
                                if n["state"] == "running"
                            )
                            total_work_done = finished_nodes + running_progress
                            percent_complete = (
                                (total_work_done / (num_nodes - cache_nodes)) * 100
                                if num_nodes
                                else 0
                            )
                            if progress_callback:
                                progress_callback(round(percent_complete, 2))

                    else:
                        if current_node and current_node == output_node:
                            output_images.setdefault(current_node, []).append(fix_image(message))
            except ConnectionClosedOK:
                pass

        try:
            await asyncio.wait_for(_recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Timed out waiting for images (prompt_id={prompt_id})") from exc

        return output_images

    def _is_localhost(self):
        server = self.server_address or ""
        return "localhost" in server or "127.0.0.1" in server or "::1" in server

    def upload_images(self, image_prompt: ImagePrompt) -> str | None:
        """
        Upload image and mask to ComfyUI server.

        Returns the real uploaded filename (including clipspace subfolder if applicable)
        that should be used as input for the workflow, or None if no upload occurred.
        """
        if not image_prompt.has_image_data():
            return None

        qimg = QImage(
            image_prompt.image_bytes,
            image_prompt.width,
            image_prompt.height,
            QImage.Format.Format_ARGB32,
        )
        image_bytes = qimage_to_bytes(qimg)

        uploaded = self.http_client.upload_file(
            "image", image_prompt.image, image_bytes, subfolder="", overwrite=True
        )

        if not uploaded:
            return None

        input_name = (
            f"{image_prompt.image} [input]"
            if self._is_localhost()
            else f"{uploaded['name']} [input]"
        )

        if not image_prompt.sel_bytes is not None:
            return input_name

        mask_qimg = reduce_alpha_by_selection(
            qimg, image_prompt.width, image_prompt.height, image_prompt.sel_bytes
        )
        mask_bytes = qimage_to_bytes(mask_qimg)

        _ = self.http_client.upload_file(
            "mask",
            image_prompt.mask,
            mask_bytes,
            subfolder="clipspace",
            ref=uploaded["name"],
            ref_subfolder=uploaded["subfolder"],
            overwrite=True,
        )

        paint_bytes = create_transparent_argb32_image(image_prompt.width, image_prompt.height)
        _ = self.http_client.upload_file(
            "image",
            image_prompt.paint,
            paint_bytes,
            subfolder="clipspace",
            ref=uploaded["name"],
            ref_subfolder=uploaded["subfolder"],
            overwrite=True,
        )

        painted_uploaded = self.http_client.upload_file(
            "image",
            image_prompt.painted,
            image_bytes,
            subfolder="clipspace",
            ref=uploaded["name"],
            ref_subfolder=uploaded["subfolder"],
            overwrite=True,
        )

        if not painted_uploaded:
            return input_name

        painted_masked_uploaded = self.http_client.upload_file(
            "mask",
            image_prompt.painted_mask,
            mask_bytes,
            subfolder="clipspace",
            ref=painted_uploaded["name"],
            ref_subfolder=painted_uploaded["subfolder"],
            overwrite=True,
        )

        if painted_masked_uploaded:
            input_name = (
                f"clipspace/{image_prompt.painted_mask} [input]"
                if self._is_localhost()
                else f"{painted_masked_uploaded['name']} [input]"
            )

        return input_name

    async def run_workflow(
        self,
        workflow: dict,
        output_node: str,
        *,
        timeout: float | None = None,
        progress_callback: Callable[[float], Any] | None = None,
    ) -> dict[str, list[bytes]]:
        """
        Execute a workflow and return the generated images.

        Note: Images must be uploaded separately via upload_images() before calling this method.
        """
        resp = self.http_client.queue_prompt(workflow, self.client_id)
        prompt_id = resp["prompt_id"]

        return await self._receive_images(
            prompt_id,
            len(workflow),
            output_node,
            timeout=timeout,
            progress_callback=progress_callback,
        )
