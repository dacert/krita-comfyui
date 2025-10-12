from krita import *
from PyQt5.Qt import *
from PyQt5.QtCore import QThread, pyqtSlot
import os
import json
import logging
from pathlib import Path
from .krita_comfyui_settings import SettingsDialog
from .config_logging import init_logging
from .worker import ComfyWorker

DOCKER_TITLE = 'Krita ComfyUi'

class KritaComfyUi(DockWidget):
    CONFIG_FILE = "config.json"

    def __init__(self):
        super().__init__()
        init_logging()
        self.logger = logging.getLogger("krita_comfyui")
        self.setWindowTitle(DOCKER_TITLE)
        self.plugin_dir = os.path.abspath(os.path.dirname(__file__))

        # load configuration once
        self.cfg = self.load_config() or {}
        
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        # Botón “Configuración”
        self.settings_btn = QPushButton("⚙️ Configuración")
        layout.addWidget(self.settings_btn)
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        # Caja de texto
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("Introduce una URL de imagen")
        layout.addWidget(self.line_edit)

        # Combo para elegir workflow (solo los configurados)
        self.workflow_combo = QComboBox()
        layout.addWidget(QLabel("Workflow seleccionado:"))
        layout.addWidget(self.workflow_combo)
        self.populate_workflow_combo()

        # Botón “Descargar”
        self.button = QPushButton("Descargar y mostrar miniatura")
        layout.addWidget(self.button)
        self.button.clicked.connect(self.conmfyui_promt)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Lista de miniaturas
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.IconMode)
        self.thumbnail_list.setIconSize(QSize(128, 128))
        self.thumbnail_list.setResizeMode(QListWidget.Adjust)
        layout.addWidget(self.thumbnail_list)

        # Botón “Añadir a Krita”
        self.add_to_krita_btn = QPushButton("Añadir imagen seleccionada a Krita")
        layout.addWidget(self.add_to_krita_btn)
        self.add_to_krita_btn.clicked.connect(self.on_add_to_krita_clicked)
       

        self.setWidget(central_widget)
        self.logger.info("KritaComfyUi loaded")

    def load_config(self):
        cfg_path = Path(os.path.join(self.plugin_dir, self.CONFIG_FILE))
        if cfg_path.exists():
            try:
                return json.loads(cfg_path.read_text())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Fallo al leer la configuración: {e}")
        return None
    
    def populate_workflow_combo(self):
        """Llena el combo con los workflows guardados en config.json."""
        self.workflow_combo.clear()
        workflows = self.cfg.get("workflows", [])
        for wf in workflows:
            name = wf.get("workflow_name")
            if name:
                self.workflow_combo.addItem(name)

    def open_settings_dialog(self):
        dlg = SettingsDialog(self.plugin_dir, parent=self)
        if dlg.exec_():
            # If the dialog was accepted we reload settings or take action here
            self.logger.info("[Settings] Cambios guardados")
            
    def conmfyui_promt(self):
        """Este método ahora solo prepara el worker y lo lanza."""
        prompt = self.line_edit.text().strip()
        if not prompt:
            self.logger.error("[KritaComfyUi] La caja está vacía.")
            QMessageBox.warning(self, "Error", "La caja está vacía.")
            return

        # Obtener URL del servidor desde la configuración (o default)
        server_url = self.cfg.get("comfyui_url", "http://127.0.0.1:8188")

         # Workflow a usar
        wf_name = self.workflow_combo.currentText()
        self.logger.info(f"[KritaComfyUi] Se ha seleccionado el workflow {wf_name}.")
        if not wf_name:
            self.logger.error("[KritaComfyUi] No se ha seleccionado workflow.")
            QMessageBox.warning(self, "Error", "No se ha seleccionado workflow.")
            return

        # Crear el worker y un hilo
        self.thread = QThread()
        self.worker = ComfyWorker(
            logger=self.logger,
            server_url=server_url,
            workflow_name=wf_name,
            prompt_text=prompt,
            cfg=self.cfg
        )

        # Conectar señales
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_images_ready)   # slot que añadirá los items
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # Empezar el hilo
        self.thread.start()

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
                item = QListWidgetItem(icon, f"{self.line_edit.text().strip()}_{idx}.png")
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

