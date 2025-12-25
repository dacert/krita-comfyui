from PyQt5.QtCore import QObject, QRunnable, pyqtSignal
import asyncio
from logging import Logger

from krita_comfyui.comfy_client.image_prompt import ImagePrompt
from ..config import Config
from ..comfy_client import ComfyClient, ComfyHttpClient
from ..prompt_builder import PromptBuilder
from ..comfy_client import find_output_node


class ComfyWorkerSignals(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(float)


class ComfyWorker(QRunnable):
    def __init__(self, logger: Logger, server_url: str, workflow_name: str,
                 prompt_text: str, cfg: Config, seed: int | None = None,
                 image_prompt: ImagePrompt | None = None):
        super().__init__()
        self.signals = ComfyWorkerSignals()
        self.logger = logger
        self.server_url = server_url
        self.workflow_name = workflow_name
        self.prompt_text = prompt_text
        self.cfg = cfg
        self.seed = seed
        self.image_prompt = image_prompt

    async def _run_async(self):
        """Async body that runs inside the thread."""
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)

        http_client = ComfyHttpClient(self.server_url)
        client = ComfyClient(self.logger, self.server_url)

        try:
            async with client as c:
                # Retrieve workflow from the server and convert it
                wf_api = http_client.get_workflow_api(self.workflow_name)
                # Build prompt using the saved configuration
                prompt_builder = PromptBuilder(self.cfg)

                image_imput_name = None
                if self.image_prompt:
                    image_imput_name = self.image_prompt.get_input_name()
                prompt = prompt_builder.build(
                    wf_api, self.workflow_name, self.prompt_text,
                    image_imput_name, self.seed
                )

                output_node = find_output_node(wf_api)
                if output_node is not None:
                    node_id, _ = output_node
                else:
                    raise Exception(
                        "No 'SaveImageWebsocket' output node found.")
                self.logger.debug(f"[ComfyWorker] Output_node: {node_id}")

                images = await c.run_workflow(
                    workflow=prompt,
                    output_node=node_id,
                    image_prompt=self.image_prompt,
                    timeout=5 * 60,
                    progress_callback=lambda p: self.signals.progress.emit(p),
                )
            self.signals.finished.emit(images)
            self.logger.debug(f"[ComfyWorker] Emit images: {len(images)}")
        except Exception as exc:
            self.signals.error.emit(str(exc))
            self.logger.exception(f"[ComfyWorker] Error {exc}")

    def run(self):
        """Method that connects to the Qt thread."""
        asyncio.run(self._run_async())
