import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Union
import logging

if __name__ != "__main__":
    from .websockets.src.websockets.exceptions import ConnectionClosedOK
    from .websockets.src.websockets import ClientConnection, connect as websockets_connect

import urllib.parse
import urllib.request


class ComfyUIClient:
    """
    Cliente asíncrono para interactuar con el servidor ComfyUI (WS + HTTP API).
    """

    def __init__(self, server: str = "127.0.0.1:8188"):
        self.server_address = server.rstrip("/")
        self.client_id = str(uuid.uuid4())
        self.ws: ClientConnection | None = None
        # Se reserva un loop propio para la clase (puedes usar el global si lo prefieres)
        self._loop = asyncio.get_event_loop()
        self.logger = logging.getLogger("krita_comfyui")

    async def __aenter__(self):
        await self._connect_ws()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    # ------------------------------------------------------------------ #
    #  Conexión WebSocket
    # ------------------------------------------------------------------ #
    async def _connect_ws(self) -> None:
        url = f"ws://{self.server_address}/ws?clientId={self.client_id}"
        self.ws = await websockets_connect(url, max_size=2**30, ping_timeout=60)
        print(f"[ComfyUIClient] WS conectado como {self.client_id}")

    # ------------------------------------------------------------------ #
    #  Métodos HTTP
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_json(file_path: Union[str, Path]) -> dict:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")

        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    async def _queue_prompt(self, prompt: dict) -> dict:
        payload = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://{self.server_address}/prompt", data=data
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    async def _get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        query = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": folder_type}
        )
        url = f"http://{self.server_address}/view?{query}"
        with urllib.request.urlopen(url) as resp:
            return resp.read()

    # ------------------------------------------------------------------ #
    #  Lógica de recepción de imágenes vía WS
    # ------------------------------------------------------------------ #

    async def _receive_images(
        self,
        prompt_id: str,
        num_nodes: int,
        *,
        timeout: float | None = None,
        progress_callback: Callable[[float], Any] | None = None
    ) -> Dict[str, List[bytes]]:
        """
        Espera a que el servidor envíe las respuestas y recopila los datos binarios
        que llegan desde el nodo `websocket_output_image`.
        """
        output_images: Dict[str, List[bytes]] = {}
        current_node: str | None = None

        async def receiver():
            nonlocal current_node
            cache_nodes = 0
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
                        if current_node == "websocket_output_image":
                            output_images.setdefault(current_node, []).append(message[8:])
            except ConnectionClosedOK:
                pass

        try:
            await asyncio.wait_for(receiver(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Timed out waiting for images (prompt_id={prompt_id})") from exc

        return output_images

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def send_prompt_and_get_images(
        self,
        workflow: Union[str, Path, dict],
        prompt_text: str,
        *,
        seed: int | None = None,
        timeout: float | None = None,
        progress_callback: Callable[[float], Any] | None = None
    ) -> Dict[str, List[bytes]]:
        """
        Envía un prompt (JSON desde disco o diccionario) y devuelve
        un `dict` con las imágenes generadas.
        """
        if isinstance(workflow, (str, Path)):
            prompt = self._load_json(workflow)
        else:
            prompt = workflow

        if not prompt_text:
            raise ValueError("El prompt_text es necesario")

        # Asumimos que los nodos están numerados de la misma forma que en el ejemplo
        prompt["6"]["inputs"]["text"] = prompt_text
        if seed is not None:
            prompt["3"]["inputs"]["seed"] = seed

        resp = await self._queue_prompt(prompt)
        prompt_id = resp["prompt_id"]

        return await self._receive_images(prompt_id, len(prompt), timeout=timeout, progress_callback=progress_callback)

    # ------------------------------------------------------------------ #
    #  Limpieza
    # ------------------------------------------------------------------ #

    async def close(self) -> None:
        """Cierra la conexión WebSocket."""
        if self.ws:
            await self.ws.close()
            print("[ComfyUIClient] WS cerrado")



# ------------------------------------------------------------------ #
#  Ejemplo de uso rápido (para ejecutar con `python -m comfyui_client`)

if __name__ == "__main__":
    from config_logging import init_logging
    from websockets.src.websockets.exceptions import ConnectionClosedOK
    from websockets.src.websockets import ClientConnection, connect as websockets_connect
    async def main():
        init_logging()
        async with ComfyUIClient("127.0.0.1:8188") as client:
            images_dict = await client.send_prompt_and_get_images(
                "workflows/qwen_text_image.json",
                "masterpiece best quality hot girl",
                seed=42,
                timeout=5 * 60,  # segundos
            )

            for node_name, imgs in images_dict.items():
                for idx, img_bytes in enumerate(imgs):
                    out_file = Path(f"{node_name}_{idx}.png")
                    out_file.write_bytes(img_bytes)
                    print(f"Guardado: {out_file}")

    asyncio.run(main())
