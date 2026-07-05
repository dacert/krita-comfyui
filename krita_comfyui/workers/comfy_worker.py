import asyncio
from logging import Logger

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from krita_comfyui.comfy_client.image_prompt import ImagePrompt

from ..comfy_client import ComfyClient, ComfyHttpClient, find_output_node
from ..config import Config
from ..prompt_builder import PromptBuilder


class SaveImageWebsocketOutputNodeNotFoundError(Exception):
    """Raised when no 'SaveImageWebsocket' output node is found in the workflow."""


class ComfyWorkerSignals(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(float)


class ComfyWorker(QRunnable):
    def __init__(
        self,
        logger: Logger,
        server_url: str,
        workflow_name: str,
        prompt_text: str,
        cfg: Config,
        seed: int | None = None,
        image_prompt: ImagePrompt | None = None,
    ):
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
        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            http_client = ComfyHttpClient(self.server_url, self.cfg.api_key)
            client = ComfyClient(self.logger, self.server_url, self.cfg.api_key)

            images: dict[str, list[bytes]] = {}
            async with client as c:
                # Retrieve workflow from the server and convert it
                wf_api = http_client.get_workflow_api(self.workflow_name)

                output_node = find_output_node(wf_api)
                if output_node is not None:
                    node_id, _ = output_node
                else:
                    raise SaveImageWebsocketOutputNodeNotFoundError(
                        "No 'SaveImageWebsocket' output node found."
                    )
                self.logger.debug(f"[ComfyWorker] Output_node: {node_id}")

                # Upload images first (before building prompt, to get real filenames)
                uploaded_image_name: str | None = None
                wf_cfg = self.cfg.get_workflow(self.workflow_name)
                if self.image_prompt and wf_cfg and wf_cfg.has_image_loader():
                    uploaded_image_name = c.upload_images(self.image_prompt)
                    self.logger.debug(f"[ComfyWorker] Image Prompt: {uploaded_image_name}")

                # Build prompt using the saved configuration
                prompt_builder = PromptBuilder(self.cfg)
                prompt = prompt_builder.build(
                    wf_api, self.workflow_name, self.prompt_text, uploaded_image_name, self.seed
                )

                self.logger.debug(f"[ComfyWorker] Promt: {prompt}")
                images = await c.run_workflow(
                    workflow=prompt,
                    output_node=node_id,
                    timeout=self.cfg.timeout_minutes * 60,
                    progress_callback=lambda p: self.signals.progress.emit(p),
                )

            self.signals.finished.emit(images)
            self.logger.debug(f"[ComfyWorker] Emit images: {len(images)}")
        except Exception as exc:
            self.signals.error.emit(str(exc))
            self.logger.exception("[ComfyWorker] Error")

    def run(self):
        """Method that connects to the Qt thread."""
        asyncio.run(self._run_async())
