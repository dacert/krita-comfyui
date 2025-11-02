import asyncio
import json
import uuid
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse
from logging import Logger

from ..websockets.src.websockets.exceptions import ConnectionClosedOK
from ..websockets.src.websockets import ClientConnection, connect as websockets_connect

from .comfy_http_client import ComfyHttpClient 

class ComfyClient:
    """
    Cliente asíncrono para interactuar con el servidor ComfyUI (WS).
    """

    def __init__(self, logger: Logger, server: str):        
        self.logger = logger        
        self.server_address = self.get_ws_host(server)
        self.http_client = ComfyHttpClient(server)
        self.client_id = str(uuid.uuid4())
        self.ws: ClientConnection | None = None

    async def __aenter__(self):
        await self._connect_ws()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()    
    
    def get_ws_host(self, url: str) -> str:
        parsed = urlparse(url)
        return f"ws://{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname

    # ------------------------------------------------------------------ #
    #  Conexión WebSocket
    # ------------------------------------------------------------------ #
    async def _connect_ws(self) -> None:
        url = f"{self.server_address}/ws?clientId={self.client_id}"
        self.ws = await websockets_connect(url, max_size=2**30, ping_timeout=60)
        self.logger.info(f"[ComfyUIClient] WS conectado como {self.client_id}")
    
    # ------------------------------------------------------------------ #
    #  Limpieza
    # ------------------------------------------------------------------ #

    async def close(self) -> None:
        """Cierra la conexión WebSocket."""
        if self.ws:
            await self.ws.close()
            self.logger.info("[ComfyUIClient] WS cerrado")
    
    # ------------------------------------------------------------------ #
    # WebSocket logic (uses the built‑in websockets module)
    # ------------------------------------------------------------------ #

    async def _receive_images(
        self,
        prompt_id: str,
        num_nodes: int,
        output_node: str,
        *,
        timeout: float | None = None,
        progress_callback: Callable[[float], Any] | None = None
    ) -> Dict[str, List[bytes]]:
        """
        Receive images from the server for a given prompt.
        """
        output_images: Dict[str, List[bytes]] = {}
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
                                if data['node'] is None:
                                    break  # Execution is done
                                else:
                                    current_node = data['node']

                        elif msg["type"] == "execution_cached":
                            cache_nodes = len(msg["data"]["nodes"])

                        elif msg["type"] == "progress_state":
                            nodes = msg["data"]["nodes"]
                            finished_nodes = sum(1 for n in nodes.values() if n.get("state") == "finished")
                            running_progress = sum(
                                n["value"] / n["max"] for n in nodes.values()
                                if n["state"] == "running"
                            )
                            total_work_done = finished_nodes + running_progress
                            percent_complete = (total_work_done / (num_nodes - cache_nodes)) * 100 if num_nodes else 0
                            if progress_callback:
                                progress_callback(round(percent_complete, 2))
                                
                    else:
                        if current_node == output_node:
                            output_images.setdefault(current_node, []).append(message[8:])
            except ConnectionClosedOK:
                pass

        try:
            await asyncio.wait_for(_recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Timed out waiting for images (prompt_id={prompt_id})") from exc

        return output_images

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def run_workflow(
        self,
        workflow: dict,
        output_node: str,
        *,
        timeout: float | None = None,
        progress_callback: Callable[[float], Any] | None = None
    ) -> Dict[str, List[bytes]]:
        
        resp = self.http_client.queue_prompt(workflow, self.client_id)
        prompt_id = resp["prompt_id"]

        return await self._receive_images(prompt_id, len(workflow), output_node, timeout=timeout, progress_callback=progress_callback)
