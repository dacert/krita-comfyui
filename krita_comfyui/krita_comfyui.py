from krita import *
from PyQt5.Qt import *
from PyQt5.QtCore import QThreadPool, pyqtSlot
import os
from pathlib import Path
from .krita_comfyui_settings import SettingsDialog
from .comfy_client import ComfyHttpClient 
from .config_logging import init_logging, getLogger
from .workers.comfy_worker import ComfyWorker
from .config import Config

DOCKER_TITLE = 'Krita ComfyUi'

class KritaComfyUi(DockWidget):
    CONFIG_FILE = "config.json"

    def __init__(self):
        super().__init__()
        init_logging()
        self.logger = getLogger("dock")

        self.setWindowTitle(DOCKER_TITLE)
        self.plugin_dir = os.path.abspath(os.path.dirname(__file__))

        self.threadpool = QThreadPool()

        # load configuration once
        self.cfg = self.load_config()
        
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        workflow_layout = QHBoxLayout()

        # Combo para elegir workflow (solo los configurados)
        self.workflow_combo = QComboBox()
        layout.addWidget(QLabel("Workflow:"))
        workflow_layout.addWidget(self.workflow_combo, stretch=1)
        self.populate_workflow_combo()
        
        # Botón “Configuración”
        self.settings_btn = QToolButton()
        settings_icon = Krita.instance().icon("configure")
        self.settings_btn.setIcon(settings_icon)
        workflow_layout.addWidget(self.settings_btn)
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        layout.addLayout(workflow_layout)

        # Caja de texto
        prompt_container = QWidget()
        prompt_layout = QHBoxLayout(prompt_container)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        self.prompt_box = QPlainTextEdit()
        self.prompt_box.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.prompt_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        font_metrics = self.prompt_box.fontMetrics()
        line_height = font_metrics.lineSpacing()
        self.prompt_box.setMinimumHeight(line_height * 3)                
        self.prompt_box.setMaximumHeight(line_height * 5)
        self.prompt_box.setPlaceholderText("Describe el contenido que quieres crear")
        prompt_layout.addWidget(self.prompt_box)
        layout.addWidget(prompt_container)

        # Botón “Descargar”
        self.create_btn = QPushButton("Generar")
        create_icon = Krita.instance().icon("tools-wizard")
        self.create_btn.setIcon(create_icon)
        layout.addWidget(self.create_btn)
        self.create_btn.clicked.connect(self.conmfyui_promt)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumHeight(5)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Lista de miniaturas
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.IconMode)
        self.thumbnail_list.setIconSize(QSize(128, 128))
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        layout.addWidget(self.thumbnail_list)

        # Botón “Añadir a Krita”
        self.apply_btn = QPushButton("Aplicar")
        apply_icon = Krita.instance().icon("dialog-ok")
        self.apply_btn.setIcon(apply_icon)
        layout.addWidget(self.apply_btn)
        self.apply_btn.clicked.connect(self.on_add_to_krita_clicked)
       

        self.setWidget(central_widget)
        self.logger.info("KritaComfyUi loaded")

    def load_config(self) -> Config:
        """Delegate configuration handling to the `Config` class."""
        cfg_path = Path(os.path.join(self.plugin_dir, self.CONFIG_FILE))
        return Config.load_or_create(cfg_path)
    
    def populate_workflow_combo(self):
        """Llena el combo con los workflows guardados en config.json
        que realmente existen en el servidor ComfyUI."""
        self.workflow_combo.clear()

        #Obtener la lista de workflows disponibles en el servidor
        try:
            http_client = ComfyHttpClient(self.cfg.comfyui_url)
            server_workflows = {
                Path(item["path"]).name for item in http_client.get_workflows_list()
                if "path" in item
            }
        except Exception as e:
            self.logger.warning(f"[KritaComfyUi] Error al consultar workflows: {e}")
            server_workflows = set()

        #Filtrar la configuración local por los nombres que existen en el servidor
        for wf in self.cfg.workflows:
            name = wf.workflow_name
            if not name:
                continue
            if name in server_workflows:
                self.workflow_combo.addItem(name)
            else:
                self.logger.info(f"[KritaComfyUi] Workflow {name} no encontrado en el servidor; omitido.")

    def open_settings_dialog(self):
        dlg = SettingsDialog(self.plugin_dir, parent=self)
        if dlg.exec_():
            # If the dialog was accepted we reload settings or take action here
            self.logger.info("[Settings] Cambios guardados")
            
    def conmfyui_promt(self):
        """Este método ahora solo prepara el worker y lo lanza."""
        prompt = self.prompt_box.toPlainText().strip()
        if not prompt:
            self.logger.error("[KritaComfyUi] La caja está vacía.")
            QMessageBox.warning(self, "Error", "La caja está vacía.")
            return

        # Obtener URL del servidor desde la configuración (o default)
        server_url = self.cfg.comfyui_url

         # Workflow a usar
        wf_name = self.workflow_combo.currentText()
        self.logger.info(f"[KritaComfyUi] Se ha seleccionado el workflow {wf_name}.")
        if not wf_name:
            self.logger.error("[KritaComfyUi] No se ha seleccionado workflow.")
            QMessageBox.warning(self, "Error", "No se ha seleccionado workflow.")
            return

        worker = ComfyWorker(
            logger=self.logger,
            server_url=server_url,
            workflow_name=wf_name,
            prompt_text=prompt,
            cfg=self.cfg
        )

        worker.signals.finished.connect(self.on_images_ready)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.progress.connect(self.on_progress)
        self.threadpool.start(worker)

    @pyqtSlot(float)
    def on_progress(self, percent: float):
        """Actualiza una barra de progreso o muestra un mensaje."""
        self.logger.info(f"Progreso: {percent:.2f}%")
        self.progress_bar.setValue(int(percent))

    @pyqtSlot(dict)
    def on_images_ready(self, images_dict: dict):
        """Slot ejecutado en el hilo principal. Añade los thumbnails."""
        self.progress_bar.setValue(0)
        for node_name, imgs in images_dict.items():
            for idx, img_bytes in enumerate(imgs):
                pixmap = QPixmap()
                if not pixmap.loadFromData(img_bytes):
                    self.logger.info(f"Imagen no válida: {node_name}_{idx}")
                    continue

                thumb = pixmap.scaled(128, 128,
                                      aspectRatioMode=Qt.KeepAspectRatio,
                                      transformMode=Qt.SmoothTransformation)

                icon = QIcon(thumb)
                item = QListWidgetItem(icon, f"{self.prompt_box.toPlainText().strip()}_{idx}.png")
                # Guardar los datos originales
                item.setData(Qt.UserRole, img_bytes)          # bytes de la imagen
                item.setData(Qt.UserRole + 1, pixmap.toImage())   # QImage

                self.thumbnail_list.addItem(item)

        self.logger.info("Generación completada")

    @pyqtSlot(str)
    def on_worker_error(self, msg: str):
        """Manejo de errores (puedes mostrar un mensaje al usuario)."""
        self.progress_bar.setValue(0)
        self.logger.error(f"[KritaComfyUi error]: {msg}")
        QMessageBox.warning(self, "Error", msg)

    def on_add_to_krita_clicked(self):
        doc = Krita.instance().activeDocument()

        selected_items = self.thumbnail_list.selectedItems()
        if not selected_items:
            self.logger.warning("[DockTextButton] Selecciona una miniatura primero.")
            return

        item = selected_items[0]
        qimage = item.data(Qt.UserRole + 1)

        if not isinstance(qimage, QImage):
            self.logger.warning("[DockTextButton] Los datos recuperados no son un QImage.")
            return
        
        if qimage.format() != QImage.Format_ARGB32:
            qimage = qimage.convertToFormat(QImage.Format_ARGB32)

        layer_name = f"Imagen {qimage.width()}x{qimage.height()}"
        new_layer = doc.createNode(layer_name, "paintLayer")
        doc.rootNode().addChildNode(new_layer, None)

        if qimage.sizeInBytes() != 4 * new_layer.channels()[0].channelSize() *  doc.width() * doc.height() :
            self.logger.info("Image size is not correct!")
            qimage = qimage.scaled(QSize(doc.width(), doc.height()), Qt.KeepAspectRatio)
        
        ptr = qimage.bits()
        ptr.setsize(qimage.byteCount())
        new_layer.setPixelData(QByteArray(ptr.asstring()), 0, 0, qimage.width() , qimage.height()) 

        #doc.setActiveNode(node)
        doc.refreshProjection()

        self.logger.warning(f"[DockTextButton] Capa creada: {layer_name}")


    def closeEvent(self, event):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.worker.close()          # si implementas un método `close` en el worker
            self.thread.quit()
            self.thread.wait()
        super().closeEvent(event)

    # notifies when views are added or removed
    # 'pass' means do not do anything
    def canvasChanged(self, canvas):
        pass
