import os
import re 
import json
import logging
from pathlib import Path
from krita import *
from PyQt5.QtWidgets import *
from .comfyui_http_client import ComfyUIHttpClient 

class SettingsDialog(QDialog):
    CONFIG_FILE = "config.json"
    WORKFLOWS_DIR = Path("workflows")  # relative to plugin_dir

    def __init__(self, plugin_dir: str, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("krita_comfyui")
        self.setWindowTitle("Configuración del Plugin")
        self.plugin_dir = Path(plugin_dir)
        self.wf_selectors = {}

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- Tab 1 – General (unchanged) ----------------------------------
        tab_general = QWidget(); tg_layout = QVBoxLayout(tab_general)
        self.comfyui_url_edit = QLineEdit()
        tg_layout.addWidget(QLabel("URL de ComfyUI:"))
        tg_layout.addWidget(self.comfyui_url_edit)
        
        self.tabs.addTab(tab_general, "General")

        # --- Tab 2 – Workflow --------------------------------------------
        self.tab_workflow = QWidget()
        wf_layout = QVBoxLayout(self.tab_workflow)

        # 1️⃣ selector de workflows
        self.workflow_combo = QComboBox()
        wf_layout.addWidget(QLabel("Seleccionar workflow:"))
        wf_layout.addWidget(self.workflow_combo)
        self.workflow_combo.currentTextChanged.connect(
            lambda _: self.populate_wf_form())   # <<<< load form on change

        # 2️⃣ contenedor para los campos del workflow
        self.wf_fields_widget = QWidget()
        self.wf_fields_layout = QFormLayout(self.wf_fields_widget)
        wf_layout.addWidget(self.wf_fields_widget)
        
        self.tabs.addTab(self.tab_workflow, "Workflow")

        # --- Botones (unchanged) -----------------------------------------
        btn_ok = QPushButton("Guardar")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accepted)
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QVBoxLayout()
        btn_layout.addWidget(btn_ok); btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        # --- Cargar configuraciones actuales -----------------------------
        self.load_config()        

    def _is_valid_url(self, url: str) -> bool:
        """Comprueba que la URL tenga un esquema http/https y al menos un dominio."""
        pattern = r'^(https?://)[^\s]+$'
        return re.match(pattern, url.strip()) is not None

    def _on_comfyui_url_changed(self):
        """Activar/desactivar la pestaña Workflow según la validez y disponibilidad del URL."""
        url = self.comfyui_url_edit.text().strip()
        if not self._is_valid_url(url):
            return
        self.load_workflow_list()

    def load_workflow_list(self):
        """Populate the combo with workflow names returned by ComfyUI's API."""
        try:
            server_url = self.comfyui_url_edit.text().strip()
            data = self._get_workflows_list(server_url)
            wf_names = sorted(
                Path(item["path"]).name for item in data if "path" in item
            )
        except Exception as e:
            self.logger.exception(e)
            QMessageBox.warning(self, "Error",
                                f"No se pudieron obtener los workflows: {e}")
            wf_names = []

        self.workflow_combo.clear()
        self.workflow_combo.addItem("— No workflow selected —")  # default

        saved_icon = Krita.instance().icon("bookmarks")
        warn_icon = Krita.instance().icon("warning")

        for name in wf_names:
            self.logger.info(name)
            item_index = self.workflow_combo.count()
            self.workflow_combo.addItem(name)

            # Find the stored configuration for this workflow (if any)
            matching_cfg = next(
                (w for w in self.workflows_cfg if w.get("workflow_name") == name),
                None,
            )

            icon_to_use = None
            font_bold = False

            if matching_cfg:
                self.logger.info(matching_cfg)
                try:
                    wf_data = self._get_workflow_api(
                        self.comfyui_url_edit.text().strip(), name
                    )
                except Exception as e:
                    self.logger.exception(e)
                    wf_data = {}
                self.logger.info(wf_data)

                missing_ref = False
                for key, prop_cfg in matching_cfg.get("inputs", {}).items():
                    node_id, inp_name = prop_cfg.get("node_id"), prop_cfg.get(
                        "property"
                    )
                    # ignorar image_loader solo si inp_name es None
                    if (key == "image_loader" and inp_name is None):
                        continue
                    
                    # Ensure key comparison is type‑agnostic (strings vs ints)
                    if (inp_name not in wf_data.get(str(node_id), {}).get("inputs", {})):
                        missing_ref = True
                        break

                font_bold = True  # bold for all stored workflows
                icon_to_use = warn_icon if missing_ref else saved_icon

            if icon_to_use:
                self.workflow_combo.setItemIcon(item_index, icon_to_use)

            if font_bold:
                model_item = self.workflow_combo.model().item(item_index)
                if model_item:
                    fnt = model_item.font()
                    fnt.setBold(True)
                    model_item.setFont(fnt)

        self.workflow_combo.setCurrentIndex(0)
        
    def load_config(self):
        """Cargar config.json con el nuevo esquema."""
        cfg_path = Path(os.path.join(self.plugin_dir, self.CONFIG_FILE))
        if not cfg_path.exists():
            return

        try:
            data = json.loads(cfg_path.read_text())
            self.comfyui_url_edit.setText(data.get("comfyui_url", ""))

            # Guardamos la lista completa para poder actualizarla más tarde
            self.workflows_cfg = data.get("workflows", [])
            
            #eliminar workflows que ya no existen en el servidor ----
            if self._is_valid_url(self.comfyui_url_edit.text().strip()):
                server_workflows = set(
                    Path(item["path"]).name for item in self._get_workflows_list(
                        self.comfyui_url_edit.text().strip()
                    ) if "path" in item
                )
                # Filtramos solo los que están en el servidor
                self.workflows_cfg = [
                    wf for wf in self.workflows_cfg if wf.get("workflow_name") in server_workflows
                ]
            
            self.comfyui_url_edit.textChanged.connect(self._on_comfyui_url_changed)
            self._on_comfyui_url_changed()
        except Exception as e:
            QMessageBox.warning(self, "Error",
                                f"Fallo al leer la configuración: {e}")

    def accepted(self):
        """Guardar la nueva configuración siguiendo el esquema actualizado."""
        cfg = {
            "comfyui_url": self.comfyui_url_edit.text().strip()
        }

        # --- Workflow ---------------------------------------------
        wf_name = self.workflow_combo.currentText()
        if wf_name and wf_name != "— No workflow selected —":
            inputs_cfg = {}
            for prop, (combo, opts) in self.wf_selectors.items():
                idx = combo.currentIndex()
                node_id, inp_name = opts[idx][1], opts[idx][2]
                inputs_cfg[prop] = {"node_id": node_id,
                                    "property": inp_name}

            wf_obj = {
                "workflow_name": wf_name,
                "inputs": inputs_cfg
            }

            # Reemplazamos o añadimos la entrada en el array
            replaced = False
            for i, existing in enumerate(self.workflows_cfg):
                if existing.get("workflow_name") == wf_name:
                    self.workflows_cfg[i] = wf_obj
                    replaced = True
                    break
            if not replaced:
                self.workflows_cfg.append(wf_obj)

        cfg["workflows"] = self.workflows_cfg

        # --- Guardar -------------------------------------------------
        try:
            cfg_path = Path(os.path.join(self.plugin_dir, self.CONFIG_FILE))
            cfg_path.write_text(json.dumps(cfg, indent=2))
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Fallo al guardar la configuración: {e}")

    # --------------------------------------------------------------------
    def populate_wf_form(self):
        """Construir el formulario con los combos usando la API en vez de archivos."""
        wf_name = self.workflow_combo.currentText()
        if not wf_name or wf_name == "— No workflow selected —":
            while self.wf_fields_layout.count():
                item = self.wf_fields_layout.takeAt(0)
                if widget := item.widget():
                    widget.deleteLater()
            return

        try:
            server_url = self.comfyui_url_edit.text().strip()
            wf_data = self._get_workflow_api(server_url, wf_name)
        except Exception as e:
            self.logger.exception(e)
            QMessageBox.warning(self, "Error", f"Cannot load workflow: {e}")
            return

        # Limpiar widgets anteriores
        while self.wf_fields_layout.count():
            item = self.wf_fields_layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()

        self.wf_selectors = {}
        for prop in ["prompt", "negative_prompt", "seed",
                        "image_loader", "num_image_sampler"]:
            combo = QComboBox()
            options = []
            options.append(("", None, None))  # valor nulo

            for node_id, node in wf_data.items():
                if isinstance(node, dict) and "inputs" in node:
                    for inp_name, _ in node["inputs"].items():
                        title = node.get("_meta", {}).get("title",
                                                            f"{node_id}")
                        label = f"{title} – {inp_name}"
                        options.append((label, node_id, inp_name))

            combo.addItems([opt[0] for opt in options])

            # pre‑seleccionar la opción guardada si existe
            wf_obj = next((w for w in self.workflows_cfg if
                            w.get("workflow_name") == wf_name), {})
            saved = wf_obj.get("inputs", {}).get(prop)
            if saved:
                try:
                    idx = next(i for i, o in enumerate(options)
                                if o[1] == saved["node_id"] and
                                    o[2] == saved["property"])
                    combo.setCurrentIndex(idx)
                except StopIteration:
                    combo.setCurrentIndex(0)

            self.wf_fields_layout.addRow(QLabel(prop + ":"), combo)
            self.wf_selectors[prop] = (combo, options)
           
        
    def _get_workflows_list(self, server_url: str) -> dict:
        http_client = ComfyUIHttpClient(server_url)
        return http_client.get_workflows_list()
                    
    def _get_workflow_api(self, server_url: str, name: str) -> dict:
        http_client = ComfyUIHttpClient(server_url)
        return http_client.get_workflow_api(name)