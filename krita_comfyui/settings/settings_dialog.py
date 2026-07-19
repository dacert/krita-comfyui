import re
from pathlib import Path

from krita import Krita  # ty:ignore[unresolved-import]
from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..comfy_client import ComfyHttpClient
from ..comfy_graph_bind.src.comfy_graph_bind import (
    EditorConfig,
    GraphEditorDialog,
    StartOutputConfig,
)
from ..config import Config, WorkflowConfig, WorkflowInput
from ..config_logging import getLogger
from ..workers import Worker


class SettingsDialog(QDialog):
    CONFIG_FILE = "krita_comfyui.config"
    WORKFLOWS_DIR = Path("workflows")  # relative to plugin_dir

    def __init__(self, plugin_dir: str, parent=None):
        super().__init__(parent)
        self._setup_basic_properties(plugin_dir)
        self._create_widgets()
        self._load_config()

    def _setup_basic_properties(self, plugin_dir: str):
        """Initial property configuration."""
        self.logger = getLogger("settings_dialog")
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 350)

        self.threadpool = QThreadPool()
        self.plugin_dir = Path(plugin_dir)
        self.http_client = None

        self.is_loading = False
        self.loaded_workflows = []
        self.start_outputs = [
            StartOutputConfig("prompt"),
            StartOutputConfig("seed", "INT"),
            StartOutputConfig("image_loader"),
        ]

    def _create_widgets(self):
        """Instantiate all UI widgets and lay them out."""
        layout = QVBoxLayout(self)

        # Tabs ------------------------------------------------------------
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._add_general_tab()
        self._add_workflow_tab()

        # Buttons ---------------------------------------------------------
        self.btn_ok = QPushButton("Ok")
        btn_cancel = QPushButton("Cancel")
        self.btn_ok.clicked.connect(self._accepted)
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _add_general_tab(self):
        """Create the “General” tab."""
        tab_general = QWidget()
        tg_layout = QVBoxLayout(tab_general)

        self.comfyui_url_edit = QLineEdit()
        tg_layout.addWidget(QLabel("ComfyUI URL:"))
        tg_layout.addWidget(self.comfyui_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        tg_layout.addWidget(QLabel("API Key (optional, for ComfyUI Cloud):"))
        tg_layout.addWidget(self.api_key_edit)

        generations_group = QGroupBox("Generation")
        gg_layout = QVBoxLayout(generations_group)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setSuffix(" min")
        gg_layout.addWidget(QLabel("Generation timeout (minutes):"))
        gg_layout.addWidget(self.timeout_spin)

        self.clipspace_checkbox = QCheckBox("Enable clipspace uploads")
        self.clipspace_checkbox.setToolTip(
            "Upload the full clipspace chain (paint, painted, mask) before running "
            "inpainting workflows. Disable only if your workflow does not use clipspace inputs."
        )
        gg_layout.addWidget(self.clipspace_checkbox)

        tg_layout.addWidget(generations_group)

        tg_layout.addStretch(1)
        self.debug_level = QCheckBox("Debug level logger")
        tg_layout.addWidget(self.debug_level)

        self.tabs.addTab(tab_general, "General")

    def _add_workflow_tab(self):
        """Create the “Workflow” tab."""
        self.tab_workflow = QWidget()
        wf_layout = QVBoxLayout(self.tab_workflow)

        # Loading indicator ------------------------------------------------
        self.loading_label = QLabel("Loading workflows …")
        wf_layout.addWidget(self.loading_label)

        # Combo & label ----------------------------------------------------
        self.workflow_combo = QComboBox()
        self.workflow_label = QLabel("Select Workflow:")
        wf_layout.addWidget(self.workflow_label)
        wf_layout.addWidget(self.workflow_combo)
        self.workflow_combo.currentTextChanged.connect(self._on_workflow_selected)
        self._set_loading(False)

        # Status -----------------------------------------------------------
        self.wf_status_label = QLabel("")
        wf_layout.addWidget(self.wf_status_label)

        # Buttons ----------------------------------------------------------
        btn_layout = QHBoxLayout()
        self.configure_btn = QPushButton("Configure Inputs…")
        self.configure_btn.clicked.connect(self._open_graph_editor)
        self.configure_btn.setEnabled(False)
        self.remove_btn = QPushButton("Remove Configuration")
        self.remove_btn.clicked.connect(self._delete_workflow_cfg)
        self.remove_btn.setEnabled(False)
        btn_layout.addWidget(self.configure_btn)
        btn_layout.addWidget(self.remove_btn)
        wf_layout.addLayout(btn_layout)

        wf_layout.addStretch(1)

        self.tabs.addTab(self.tab_workflow, "Workflow")
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _run_worker(self, fn, *args, on_success=None, on_error=None):
        worker = Worker(fn, *args)
        if on_success:
            worker.signals.finished.connect(on_success)
        if on_error:
            worker.signals.error.connect(on_error)
        self.threadpool.start(worker)

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
            ^(?P<scheme>http|https)://                # http:// or https://
            (?P<host>
                (?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}      # domain like example.com
                |
                \d{1,3}(?:\.\d{1,3}){3}               # IPv4 address
                |
                localhost                             # localhost
            )
            (?::(?P<port>\d{1,5}))?                   # optional :port
            $""",
            re.VERBOSE,
        )

        match = pattern.match(url.strip())
        if not match:
            return False

        port_str = match.group("port")
        if port_str is None:  # no explicit port provided
            # Allow URLs without a port;
            # defaults (80/443) will be handled by the client.
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
        if not self.is_loading:
            self._set_loading(True)
            self._run_worker(
                self._get_workflows,
                on_success=lambda d: (self._populate_workflow_combo(d), self._set_loading(False)),
                on_error=lambda: (
                    QMessageBox.warning(
                        self, "Error", "Could not retrieve the configured workflows."
                    ),
                    self._set_loading(False),
                ),
            )

    def _get_workflows(self):
        server_list = self._get_workflows_list(self.cfg.comfyui_url)
        wf_names = sorted(Path(item["path"]).name for item in server_list if "path" in item)
        cfg_names = {w.workflow_name for w in self.cfg.workflows}
        return [(name, name in cfg_names) for name in wf_names]

    def _populate_workflow_combo(self, workflows):
        """Populate the combo with workflow names returned by ComfyUI's API."""
        self.workflow_combo.clear()
        self.workflow_combo.addItem("— No workflow selected —")  # default

        saved_icon = Krita.instance().icon("bookmarks")

        self.loaded_workflows = workflows
        for name, isSaved in workflows:
            item_index = self.workflow_combo.count()
            self.workflow_combo.addItem(name)

            if isSaved:
                self.workflow_combo.setItemIcon(item_index, saved_icon)
                model_item = self.workflow_combo.model().item(item_index)
                if model_item:
                    fnt = model_item.font()
                    fnt.setBold(True)
                    model_item.setFont(fnt)

        self.workflow_combo.setCurrentIndex(0)

    def _on_comfyui_url_changed(self):
        """
        Enable/disable the Workflow tab based on URL validity and availability.
        """
        url = self.comfyui_url_edit.text().strip()
        if not self._is_valid_url(url):
            self.comfyui_url_edit.setStyleSheet("border: 1px solid #320a0c;")
            self.comfyui_url_edit.setToolTip("Invalid URL format.")
            self.btn_ok.setEnabled(False)
            self.tabs.setTabEnabled(1, False)
            return

        self.comfyui_url_edit.setStyleSheet("")
        self.comfyui_url_edit.setToolTip("")
        self.btn_ok.setEnabled(True)
        self.tabs.setTabEnabled(1, True)
        self.cfg.comfyui_url = url

    def _on_debug_level_change(self):
        self.cfg.logger = self.debug_level.isChecked()

    def _on_api_key_changed(self):
        self.cfg.api_key = self.api_key_edit.text().strip()

    def _on_timeout_changed(self):
        self.cfg.timeout_minutes = self.timeout_spin.value()

    def _on_clipspace_changed(self):
        self.cfg.clipspace_enabled = self.clipspace_checkbox.isChecked()

    def _load_config(self):
        """Load krita_comfyui.config with the new schema."""
        cfg_path = Path(self.plugin_dir, self.CONFIG_FILE)
        self.cfg = Config.load_or_create(cfg_path)

        self.debug_level.setChecked(self.cfg.logger)
        self.debug_level.stateChanged.connect(self._on_debug_level_change)
        self.comfyui_url_edit.setText(self.cfg.comfyui_url)
        self.comfyui_url_edit.textChanged.connect(self._on_comfyui_url_changed)
        self.api_key_edit.setText(self.cfg.api_key)
        self.api_key_edit.textChanged.connect(self._on_api_key_changed)
        self.timeout_spin.setValue(self.cfg.timeout_minutes)
        self.timeout_spin.valueChanged.connect(self._on_timeout_changed)
        self.clipspace_checkbox.setChecked(self.cfg.clipspace_enabled)
        self.clipspace_checkbox.stateChanged.connect(self._on_clipspace_changed)

    def _on_workflow_selected(self):
        """Update UI when a workflow is selected in the combo box."""
        wf_name = self.workflow_combo.currentText()
        if not wf_name or wf_name == "— No workflow selected —":
            self.wf_status_label.setText("")
            self.configure_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)
            return

        is_saved = any(w.workflow_name == wf_name for w in self.cfg.workflows)
        self.wf_status_label.setText("✓ Configured" if is_saved else "— Not configured")
        self.configure_btn.setEnabled(True)
        self.remove_btn.setEnabled(is_saved)

    def _open_graph_editor(self):
        """Open the visual graph editor dialog for the selected workflow."""
        wf_name = self.workflow_combo.currentText()
        if wf_name == "— No workflow selected —":
            return

        try:
            wf_data = self._get_workflow_api(self.cfg.comfyui_url, wf_name)
        except Exception:
            self.logger.exception("Cannot load workflow:")
            QMessageBox.warning(self, "Error", "Cannot load workflow")
            return

        cfg_obj = next((w for w in self.cfg.workflows if w.workflow_name == wf_name), None)

        config = EditorConfig(
            workflow_name=wf_name,
            start_node_title="Krita Inputs",
            start_outputs=self.start_outputs,
        )

        dialog = GraphEditorDialog.from_api_workflow(
            wf_data,
            config,
            initial_result=self._config_to_initial_result(cfg_obj),
            parent=self,
        )
        dialog.setWindowTitle(f"Configure — {wf_name}")
        if dialog.exec_() != GraphEditorDialog.Accepted:
            return

        result = dialog.editor_result()
        if result is None:
            return

        inputs_cfg = {
            name: WorkflowInput(node_id=entry["node_id"], property=entry["property"])
            for name, entry in result.get("inputs", {}).items()
        }
        wf_obj = WorkflowConfig(workflow_name=wf_name, inputs=inputs_cfg)

        replaced = False
        for i, existing in enumerate(self.cfg.workflows):
            if existing.workflow_name == wf_name:
                self.cfg.workflows[i] = wf_obj
                replaced = True
                break
        if not replaced:
            self.cfg.workflows.append(wf_obj)

        self._populate_workflow()

    def _delete_workflow_cfg(self):
        """Remove the currently selected workflow configuration from `self.cfg`."""
        wf_name = self.workflow_combo.currentText()
        if wf_name == "— No workflow selected —":
            return

        self.cfg.workflows = [w for w in self.cfg.workflows if w.workflow_name != wf_name]
        self._populate_workflow()

    @staticmethod
    def _config_to_initial_result(cfg_obj: WorkflowConfig | None) -> dict | None:
        """Convert a WorkflowConfig to the initial_result format expected by GraphEditorDialog."""
        if cfg_obj is None:
            return None
        return {
            "workflow_name": cfg_obj.workflow_name,
            "inputs": {
                name: {"node_id": inp.node_id, "property": inp.property}
                for name, inp in cfg_obj.inputs.items()
            },
        }

    def _accepted(self):
        """Persist the current dialog state into Config."""
        try:
            cfg_path = Path(self.plugin_dir, self.CONFIG_FILE)
            self.cfg.save(cfg_path)  # only save the existing self.cfg
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")

    def _get_http_client(self, server_url: str):
        if self.http_client is None or self.http_client.server_address != server_url:
            self.http_client = ComfyHttpClient(server_url, self.cfg.api_key)
        return self.http_client

    def _get_workflows_list(self, server_url: str) -> dict:
        return self._get_http_client(server_url).get_workflows_list()

    def _get_workflow_api(self, server_url: str, name: str) -> dict:
        return self._get_http_client(server_url).get_workflow_api(name)
