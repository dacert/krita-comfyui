import re
from pathlib import Path
from krita import *
from PyQt5.QtWidgets import *

from .config_logging import getLogger

from .config import Config, WorkflowConfig, WorkflowInput
from .comfy_client import ComfyHttpClient 

class SettingsDialog(QDialog):
    CONFIG_FILE = "config.json"
    WORKFLOWS_DIR = Path("workflows")  # relative to plugin_dir

    def __init__(self, plugin_dir: str, parent=None):
        super().__init__(parent)
        self.logger = getLogger("settings_dialog")
        self.setWindowTitle("Configuración del Plugin")
        self.setMinimumSize(600, 350)

        self.plugin_dir = Path(plugin_dir)
        self.http_client = None

        self.is_loading = False
        self.loaded_workflows = []
        self.wf_selectors = {}

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        tab_general = QWidget(); tg_layout = QVBoxLayout(tab_general)
        self.comfyui_url_edit = QLineEdit()
        tg_layout.addWidget(QLabel("URL de ComfyUI:"))
        tg_layout.addWidget(self.comfyui_url_edit)
        tg_layout.addStretch(1) 
        
        self.tabs.addTab(tab_general, "General")

        self.tab_workflow = QWidget()
        wf_layout = QVBoxLayout(self.tab_workflow)

        self.loading_label = QLabel("Loading workflows …")
        wf_layout.addWidget(self.loading_label)

        self.workflow_combo = QComboBox()
        self.workflow_label = QLabel("Seleccionar workflow:")
        wf_layout.addWidget(self.workflow_label)
        wf_layout.addWidget(self.workflow_combo)
        self.workflow_combo.currentTextChanged.connect(
            lambda _: self.populate_wf_form())
        self._set_loading(False)

        self.wf_fields_widget = QWidget()
        self.wf_fields_layout = QFormLayout(self.wf_fields_widget)
        wf_layout.addWidget(self.wf_fields_widget)        
        wf_layout.addStretch(1)
        
        self.tabs.addTab(self.tab_workflow, "Workflow")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.btn_ok = QPushButton("Ok")
        btn_cancel = QPushButton("Cancel")
        self.btn_ok.clicked.connect(self.accepted)
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch() 
        btn_layout.addWidget(self.btn_ok); btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.load_config()
    
    def _set_loading(self, val: bool):
        self.is_loading = val
        self.loading_label.setVisible(val)
        self.workflow_combo.setVisible(not val)
        self.workflow_label.setVisible(not val)

    def _is_valid_url(self, url: str) -> bool:
        """
        Validates an URL.
        - Scheme must be http or https.
        - Host can be:
            • domain with at least one dot (e.g. example.com)
            • IPv4 address
            • literal 'localhost'
        - Port is optional; if omitted, defaults are accepted.
        """
        pattern = re.compile(
            r"""
            ^(?P<scheme>http|https)://                       # http:// or https://
            (?P<host>
                (?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}             # domain like example.com
                |
                \d{1,3}(?:\.\d{1,3}){3}                      # IPv4 address
                |
                localhost                                    # localhost
            )
            (?::(?P<port>\d{1,5}))?                          # optional :port
            $""",
            re.VERBOSE,
        )

        match = pattern.match(url.strip())
        if not match:
            return False

        port_str = match.group("port")
        if port_str is None:  # no explicit port provided
            # Allow URLs without a port; defaults (80/443) will be handled by the client.
            pass
        else:
            port = int(port_str)
            if not (0 < port <= 65535):
                return False

        host = match.group("host")
        # Only validate octets for real IPv4 addresses, skip 'localhost'
        if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", host):
            parts = host.split(".")
            if any(int(p) > 255 for p in parts):
                return False

        return True

    def _on_tab_changed(self, index: int):
        """Called whenever the active tab changes."""
        if index == 1:
            self._populate_workflow()
    
    def _populate_workflow(self):
        try:
            if not self.is_loading and len(self.loaded_workflows) == 0:
                self._set_loading(True)
                workflows = self._get_workflows()
                self._populate_workflow_combo(workflows)
        except Exception as e:
            self.logger.exception(e)
            QMessageBox.warning(self, "Error",
                                f"No se pudieron obtener los workflows configurados: {e}")
        finally:
            self._set_loading(False)

    def _get_workflows(self):
        server_list = self._get_workflows_list(self.cfg.comfyui_url)
        wf_names = sorted(
            Path(item["path"]).name for item in server_list if "path" in item
        )
        cfg_map = {w.workflow_name: w for w in self.cfg.workflows}
        results = [self._fetch_single_workflow(name, self.cfg.comfyui_url, cfg_map.get(name)) for name in wf_names]
        return results

    def _fetch_single_workflow(
        self, name: str, server_url: str, matching_cfg=None
    ):
        missing_ref = False
        saved = False
        wf_data = None

        if matching_cfg:
            saved = True
            try:
                wf_data = self._get_workflow_api(server_url, name)
            except Exception as e:
                self.logger.exception(e)
            for key, prop_cfg in matching_cfg.inputs.items():
                node_id, inp_name = prop_cfg.node_id, prop_cfg.property
                if key == "image_loader" and inp_name is None:
                    continue
                if (wf_data is None or inp_name not in wf_data.get(str(node_id), {}).get("inputs", {})):
                    missing_ref = True
                    break           

        return (name, saved, missing_ref, wf_data)
    
    def _populate_workflow_combo(self, workflows):
        """Populate the combo with workflow names returned by ComfyUI's API."""        
        self.workflow_combo.clear()
        self.workflow_combo.addItem("— No workflow selected —")  # default

        saved_icon = Krita.instance().icon("bookmarks")
        warn_icon = Krita.instance().icon("warning")

        self.loaded_workflows = workflows
        for (name, isSaved, missing_ref, _) in workflows:
            item_index = self.workflow_combo.count()
            self.workflow_combo.addItem(name)

            icon_to_use = None
            if isSaved:
                icon_to_use = warn_icon if missing_ref else saved_icon

            if icon_to_use:
                self.workflow_combo.setItemIcon(item_index, icon_to_use)

            if isSaved:
                model_item = self.workflow_combo.model().item(item_index)
                if model_item:
                    fnt = model_item.font()
                    fnt.setBold(True)
                    model_item.setFont(fnt)

        self.workflow_combo.setCurrentIndex(0)
            
    def _on_comfyui_url_changed(self):
        """Activar/desactivar la pestaña Workflow según la validez y disponibilidad del URL."""
        url = self.comfyui_url_edit.text().strip()
        if not self._is_valid_url(url):
            self.comfyui_url_edit.setStyleSheet("border: 1px solid #320a0c;")
            self.comfyui_url_edit.setToolTip("Invalid url format.")
            self.btn_ok.setEnabled(False)
            self.tabs.setTabEnabled(1, False)
            return

        self.comfyui_url_edit.setStyleSheet("")
        self.comfyui_url_edit.setToolTip("")
        self.btn_ok.setEnabled(True)
        self.tabs.setTabEnabled(1, True)
        self.cfg.comfyui_url = url
        
    def load_config(self):
        """Cargar config.json con el nuevo esquema."""
        cfg_path = Path(self.plugin_dir, self.CONFIG_FILE)
        self.cfg = Config.load_or_create(cfg_path)            
        self.comfyui_url_edit.setText(self.cfg.comfyui_url)            
        self.comfyui_url_edit.textChanged.connect(self._on_comfyui_url_changed)

    def accepted(self):
        """Persist the current dialog state into Config."""
        cfg = Config(
            comfyui_url=self.comfyui_url_edit.text().strip(),
            workflows=list(self.cfg.workflows),  # keep existing entries
        )

        wf_name = self.workflow_combo.currentText()
        if wf_name and wf_name != "— No workflow selected —":
            inputs_cfg = {}
            for prop, (combo, opts) in self.wf_selectors.items():
                idx = combo.currentIndex()
                node_id, inp_name = opts[idx][1], opts[idx][2]
                inputs_cfg[prop] = WorkflowInput(node_id=node_id, property=inp_name)

            wf_obj = WorkflowConfig(
                workflow_name=wf_name,
                inputs=inputs_cfg
            )

            # Replace or append the entry in cfg.workflows
            replaced = False
            for i, existing in enumerate(cfg.workflows):
                if existing.workflow_name == wf_name:
                    cfg.workflows[i] = wf_obj
                    replaced = True
                    break
            if not replaced:
                cfg.workflows.append(wf_obj)

        # Persist to disk
        try:
            cfg_path = Path(self.plugin_dir, self.CONFIG_FILE)
            cfg.save(cfg_path)
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
            wf_data = next((w[-1] for w in self.loaded_workflows if
                                w[0] == wf_name ), {})
            if not wf_data:
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
            wf_obj = next((w for w in self.cfg.workflows if
                            w.workflow_name == wf_name), None)
            saved = wf_obj.inputs.get(prop) if wf_obj else None
            if saved:
                try:
                    idx = next(i for i, o in enumerate(options)
                                if o[1] == saved.node_id and
                                    o[2] == saved.property)
                    combo.setCurrentIndex(idx)
                except StopIteration:
                    combo.setCurrentIndex(0)

            self.wf_fields_layout.addRow(QLabel(prop + ":"), combo)
            self.wf_selectors[prop] = (combo, options)
           
        
    def get_http_client(self, server_url: str):
        if self.http_client is None or self.http_client.server_address != server_url:
            self.http_client = ComfyHttpClient(server_url)
        return self.http_client
            
    def _get_workflows_list(self, server_url: str) -> dict:
        return self.get_http_client(server_url).get_workflows_list()
                    
    def _get_workflow_api(self, server_url: str, name: str) -> dict:
        return self.get_http_client(server_url).get_workflow_api(name)