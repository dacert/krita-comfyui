from krita import *
from PyQt5.Qt import *
from PyQt5.QtCore import QThread, pyqtSlot
import os
import logging
from .config_logging import init_logging
from .worker import ComfyWorker

DOCKER_TITLE = 'Krita ComfyUi'

class KritaComfyUi(DockWidget):

    def __init__(self):
        super().__init__()
        init_logging()
        self.logger = logging.getLogger("krita_comfyui")
        self.setWindowTitle(DOCKER_TITLE)
        self.plugin_dir = os.path.abspath(os.path.dirname(__file__))

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        # Caja de texto
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("Introduce una URL de imagen")
        layout.addWidget(self.line_edit)

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
        
    def conmfyui_promt(self):
        """Este método ahora solo prepara el worker y lo lanza."""
        prompt = self.line_edit.text().strip()
        if not prompt:
            self.logger.error("[DockTextButton] La caja está vacía.")
            raise ValueError("[DockTextButton] La caja está vacía.")

        # Ruta al workflow (puede ser absoluta o relativa)
        workflow_path = os.path.join(self.plugin_dir, "workflows/qwen_text_image.json")

        # Crear el worker y un hilo
        self.thread = QThread()                 # guardamos la referencia para evitar que se recolecte
        self.worker = ComfyWorker(workflow_path, prompt)

        self.logger.info("This is an info message. conmfyui_promt")

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
        self.logger.error(f"[ComfyWorker error]: {msg}")

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

