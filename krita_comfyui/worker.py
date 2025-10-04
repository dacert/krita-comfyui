from PyQt5.QtCore import QObject, pyqtSignal
import random
import asyncio
import logging
from .comfyui_client import ComfyUIClient

class ComfyWorker(QObject):
    finished = pyqtSignal(dict)      # dict de imágenes generadas
    error    = pyqtSignal(str)       # mensaje de error
    progress = pyqtSignal(float)

    def __init__(self, workflow_path: str, prompt_text: str,
                 seed: int | None = None, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("krita_comfyui")
        self.workflow_path = workflow_path
        self.prompt_text  = prompt_text
        self.seed         = seed

    async def _run_async(self):
        """Cuerpo asíncrono que se ejecuta dentro del hilo."""
        # --- 1. Creamos un loop propio para este thread -----------------
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)

        client = ComfyUIClient(server="127.0.0.1:8188")

        try:
            # --- 2. Abrimos la conexión WS con el context manager ----
            async with client as c:
                seed_val = self.seed if self.seed is not None else random.randint(1, 11768320141)
                
                def _progress_cb(percent: float):
                   self.progress.emit(percent)

                images = await c.send_prompt_and_get_images(
                    workflow=self.workflow_path,
                    prompt_text=self.prompt_text,
                    seed=seed_val,
                    timeout=5 * 60,          # segundos
                    progress_callback=_progress_cb
                )
            # --- 3. Emitimos los resultados ----------------------------
            self.finished.emit(images)
            self.logger.info(f"emit images: {len(images)}")
        except Exception as exc:
            # Propagamos la excepción al slot de error y guardamos en log
            self.error.emit(str(exc))
            self.logger.exception(f"_run_async Error {exc}")
        finally:
            await client.close()          # Cierra WS si no se usó el context manager

    def run(self):
        """Método que se conecta al hilo de Qt."""
        asyncio.run(self._run_async())

