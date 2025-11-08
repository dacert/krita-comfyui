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

        # Combo to choose workflow (only the configured ones)
        self.workflow_combo = QComboBox()
        layout.addWidget(QLabel("Workflow:"))
        workflow_layout.addWidget(self.workflow_combo, stretch=1)
        self.populate_workflow_combo()
        
        # “Settings” button
        self.settings_btn = QToolButton()
        settings_icon = Krita.instance().icon("configure")
        self.settings_btn.setIcon(settings_icon)
        workflow_layout.addWidget(self.settings_btn)
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        layout.addLayout(workflow_layout)

        # Text box
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
        self.prompt_box.setPlaceholderText("Describe the content you want to create")
        prompt_layout.addWidget(self.prompt_box)
        layout.addWidget(prompt_container)

        # Generate button
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

        # Thumbnail list
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.IconMode)
        self.thumbnail_list.setIconSize(QSize(128, 128))
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        layout.addWidget(self.thumbnail_list)

        # “Apply to Krita” button
        self.apply_btn = QPushButton("Apply")
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
        """Fill the combo with workflows stored in config.json
        that actually exist on the Comfy server."""
        self.workflow_combo.clear()

        # Obtain the list of available workflows on the server
        try:
            http_client = ComfyHttpClient(self.cfg.comfyui_url)
            server_workflows = {
                Path(item["path"]).name for item in http_client.get_workflows_list()
                if "path" in item
            }
        except Exception as e:
            self.logger.warning(f"[KritaComfyUi] Error querying workflows: {e}")
            server_workflows = set()

        # Filter local config by names that exist on the server
        for wf in self.cfg.workflows:
            name = wf.workflow_name
            if not name:
                continue
            if name in server_workflows:
                self.workflow_combo.addItem(name)
            else:
                self.logger.info(f"[KritaComfyUi] Workflow {name} not found on the server; omitted.")

    def open_settings_dialog(self):
        dlg = SettingsDialog(self.plugin_dir, parent=self)
        if dlg.exec_():
            self.cfg = self.load_config()
            self.populate_workflow_combo()
            self.logger.info("[Settings] Changes saved")
            
    def conmfyui_promt(self):
        """Prepares the worker and starts it."""
        prompt = self.prompt_box.toPlainText().strip()
        if not prompt:
            self.logger.error("[KritaComfyUi] The box is empty.")
            QMessageBox.warning(self, "Error", "The box is empty.")
            return

        # Get server URL from configuration (or default)
        server_url = self.cfg.comfyui_url

        # Workflow to use
        wf_name = self.workflow_combo.currentText()
        self.logger.info(f"[KritaComfyUi] Selected workflow {wf_name}")
        if not wf_name:
            self.logger.error("[KritaComfyUi] No workflow selected.")
            QMessageBox.warning(self, "Error", "No workflow selected.")
            return
        
        self.create_btn.setEnabled(False)

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
        """Update a progress bar or display a message."""
        self.logger.info(f"Progress: {percent:.2f}%")
        self.progress_bar.setValue(int(percent))

    @pyqtSlot(dict)
    def on_images_ready(self, images_dict: dict):
        """Slot executed in the main thread. Adds thumbnails."""
        self.progress_bar.setValue(0)
        self.create_btn.setEnabled(True)
        for node_name, imgs in images_dict.items():
            for idx, img_bytes in enumerate(imgs):
                pixmap = QPixmap()
                if not pixmap.loadFromData(img_bytes):
                    self.logger.info(f"Invalid image: {node_name}_{idx}")
                    continue

                thumb = pixmap.scaled(128, 128,
                                      aspectRatioMode=Qt.KeepAspectRatio,
                                      transformMode=Qt.SmoothTransformation)

                icon = QIcon(thumb)
                item = QListWidgetItem(icon, f"{self.prompt_box.toPlainText().strip()}_{idx}.png")
                # Store original data
                item.setData(Qt.UserRole, img_bytes)          # image bytes
                item.setData(Qt.UserRole + 1, pixmap.toImage())   # QImage

                self.thumbnail_list.addItem(item)

        self.logger.info("Generation completed")

    @pyqtSlot(str)
    def on_worker_error(self, msg: str):
        """Error handling."""
        self.progress_bar.setValue(0)
        self.create_btn.setEnabled(True)
        self.logger.error(f"[KritaComfyUi] error: {msg}")
        QMessageBox.warning(self, "Error", msg)

    def on_add_to_krita_clicked(self):
        doc = Krita.instance().activeDocument()

        selected_items = self.thumbnail_list.selectedItems()
        if not selected_items:
            self.logger.warning("[KritaComfyUi] Select a thumbnail first.")
            return

        item = selected_items[0]
        qimage = item.data(Qt.UserRole + 1)

        if not isinstance(qimage, QImage):
            self.logger.warning("[KritaComfyUi] Retrieved data is not a QImage.")
            return
        
        if qimage.format() != QImage.Format_ARGB32:
            qimage = qimage.convertToFormat(QImage.Format_ARGB32)

        layer_name = f"Image {qimage.width()}x{qimage.height()}"
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

        self.logger.warning(f"[KritaComfyUi] Layer created: {layer_name}")

    def closeEvent(self, event):
        self.threadpool.clear()
        super().closeEvent(event)

    # notifies when views are added or removed
    # 'pass' means do not do anything
    def canvasChanged(self, canvas):
        pass
