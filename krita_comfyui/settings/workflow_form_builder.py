from collections.abc import Callable

from PyQt5.QtCore import pyqtBoundSignal
from PyQt5.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QWidget

from ..config import WorkflowConfig


class WorkflowFormBuilder:
    """
    Builds a QFormLayout with combo boxes for each workflow property
    (prompt, negative_prompt, seed, image_loader, num_image_sampler)
    based on data returned from ComfyUI’s API.

    The builder keeps references to the selectors so that SettingsDialog
    can read/write values without having to know the underlying layout.
    """

    PROPERTIES = (
        "prompt",
        # "negative_prompt",
        "seed",
        "image_loader",
        # "num_image_sampler",
    )

    OPTIONAL_PROPERTIES = (
        "image_loader",
        "num_image_sampler",
        "negative_prompt",
    )

    def __init__(self, parent: QWidget):
        self.parent = parent
        self.layout = QFormLayout(parent)
        self.selectors = {}  # prop -> (QComboBox, options list)

    def clear(self):
        """Remove all widgets from the form."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item and (widget := item.widget()):
                widget.deleteLater()
        self.selectors.clear()

    def build_from_api(
        self,
        wf_data: dict,
        cfg_obj: WorkflowConfig | None,
    ) -> None:
        """
        Populate the form using `wf_data` (the API response for a workflow)
        and optionally pre‑select values from an existing config object.
        """
        self.clear()

        for prop in self.PROPERTIES:
            combo = QComboBox()
            options = [("", None, None)]  # null value

            for node_id, node in wf_data.items():
                if isinstance(node, dict) and "inputs" in node:
                    for inp_name in node["inputs"]:
                        title = node.get("_meta", {}).get("title", f"{node_id}")
                        label = f"{title} – {inp_name}"
                        options.append((label, node_id, inp_name))

            combo.addItems([opt[0] for opt in options])

            # Pre‑select if a config exists
            saved = cfg_obj.inputs.get(prop) if cfg_obj else None
            if saved:
                try:
                    idx = next(
                        i
                        for i, o in enumerate(options)
                        if o[1] == saved.node_id and o[2] == saved.property
                    )
                    combo.setCurrentIndex(idx)
                except StopIteration:
                    combo.setCurrentIndex(0)

            required = prop not in self.OPTIONAL_PROPERTIES
            self.layout.addRow(QLabel(f"{'*' if required else ''}{prop}:"), combo)
            self.selectors[prop] = (combo, options)

    def add_action_buttons(
        self,
        update_cb: Callable[..., None] | pyqtBoundSignal,
        delete_cb: Callable[..., None] | pyqtBoundSignal,
        can_delete: bool,
    ) -> None:
        """
        Append the Add/Update and Remove buttons below the form.
        `can_delete` enables/disables the Delete button.
        """
        btn_update = QPushButton("Add/Update")
        btn_update.clicked.connect(update_cb)

        btn_delete = QPushButton("Remove")
        btn_delete.setEnabled(can_delete)
        btn_delete.clicked.connect(delete_cb)

        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(btn_update)
        hbox.addWidget(btn_delete)

        self.layout.addRow(QLabel(), hbox)
