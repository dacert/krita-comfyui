from PyQt5.QtCore import QObject, pyqtSignal
import asyncio
from  logging import Logger

from .config import Config
from .comfy_client import ComfyClient, ComfyHttpClient
from .prompt_builder import PromptBuilder
from .comfy_client import find_output_node

class ComfyWorker(QObject):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)
    progress = pyqtSignal(float)

    def __init__(self, logger: Logger, server_url: str, workflow_name: str,
                 prompt_text: str, cfg: Config, seed: int | None = None, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.server_url = server_url
        self.workflow_name = workflow_name
        self.prompt_text  = prompt_text
        self.cfg = cfg
        self.seed         = seed

    async def _run_async(self):
        """Cuerpo asíncrono que se ejecuta dentro del hilo."""        
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)

        http_client = ComfyHttpClient(self.server_url)
        client = ComfyClient(self.logger, self.server_url)

        try:
            async with client as c:
                # Obtener workflow desde el servidor y convertirlo
                wf_api = http_client.get_workflow_api(self.workflow_name)
                # Construir prompt usando la configuración guardada
                prompt_builder = PromptBuilder(self.cfg)
                prompt = prompt_builder.build(wf_api, self.workflow_name, self.prompt_text, self.seed)

                output_node = find_output_node(wf_api)
                if output_node is not None:
                    node_id, _ = output_node
                else:
                    raise Exception("No se encontró ningún nodo de tipo 'SaveImageWebsocket' para el output.")
                self.logger.info(f"[ComfyWorker] Output_node: {node_id}")

                images = await c.run_workflow(
                    workflow=prompt,
                    output_node=node_id,
                    timeout=5 * 60,
                    progress_callback=lambda p: self.progress.emit(p),
                )
            self.finished.emit(images)
            self.logger.info(f"[ComfyWorker] Emit images: {len(images)}")
        except Exception as exc:
            self.error.emit(str(exc))
            self.logger.exception(f"[ComfyWorker] Error {exc}")

    def run(self):
        """Método que se conecta al hilo de Qt."""   
        asyncio.run(self._run_async())

