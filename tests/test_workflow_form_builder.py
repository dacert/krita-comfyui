import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QWidget

from krita_comfyui.settings.workflow_form_builder import WorkflowFormBuilder


class DummyConfig:
    """
    Minimal stub for `WorkflowConfig`.  It only needs an `inputs` mapping that
    resolves to objects with ``node_id`` and ``property`` attributes.
    """

    def __init__(self, inputs=None):
        self.inputs = inputs or {}


# --------------------------------------------------------------------------- #
# Helper: create a minimal workflow API dict --------------------------------- #
def make_wf_data(node_specs):
    """
    Create a dictionary that mimics the structure returned by ComfyUI’s API.

    Parameters
    ----------
    node_specs : list[tuple[str, str]]
        Each tuple contains (node_id, input_name).  The function will create
        a node dict with an ``inputs`` key and a ``_meta.title`` entry.
    """
    wf = {}
    for node_id, inp in node_specs:
        wf[node_id] = {"inputs": {inp: None}, "_meta": {"title": f"Node{node_id}"}}
    return wf


# --------------------------------------------------------------------------- #
# Fixtures ----------------------------------------------------------------- #
@pytest.fixture
def app(qtbot):
    """Ensure a QApplication instance exists."""
    return qtbot.addWidget(QWidget())  # el widget se mantendrá hasta que termine el test


@pytest.fixture
def parent_widget(app):
    """A dummy QWidget that will act as the parent of the form builder."""
    return QWidget()


@pytest.fixture
def builder(parent_widget):
    return WorkflowFormBuilder(parent_widget)


# --------------------------------------------------------------------------- #
# Tests -------------------------------------------------------------------- #
def test_build_from_api_populates_selectors(builder):
    """
    Verify that `build_from_api` creates a selector for each property in
    PROPERTIES and populates it with the correct options.
    """
    wf_data = make_wf_data([
        ("a", "inp1"),
        ("b", "inp2"),
    ])

    builder.build_from_api(wf_data, cfg_obj=None)

    # All declared properties should have a selector (including optional ones)
    expected_props = set(builder.PROPERTIES)
    assert set(builder.selectors.keys()) == expected_props

    for combo, options in builder.selectors.values():
        # The first option should be the null value
        assert options[0] == ("", None, None)
        # Remaining options come from wf_data
        expected_labels = [
            f"Node{node_id} – {inp}" for node_id, inp in [("a", "inp1"), ("b", "inp2")]
        ]
        actual_labels = [opt[0] for opt in options[1:]]
        assert set(actual_labels) == set(expected_labels)
        # The combo should contain the same number of items
        assert combo.count() == len(options)


def test_preselection_with_config(builder):
    """
    When a `WorkflowConfig` is supplied, the selector should pre‑select the
    matching option.  If the config value cannot be found, it defaults to null.
    """
    wf_data = make_wf_data([("x", "prop")])
    # Config pointing to existing node/property
    cfg_existing = DummyConfig({"prompt": type("Obj", (), {"node_id": "x", "property": "prop"})()})
    builder.build_from_api(wf_data, cfg_obj=cfg_existing)
    combo_prompt, _ = builder.selectors["prompt"]
    # The first non‑null option should be selected
    assert combo_prompt.currentIndex() == 1

    # Config pointing to a missing node/property
    cfg_missing = DummyConfig({"seed": type("Obj", (), {"node_id": "z", "property": "missing"})()})
    builder.build_from_api(wf_data, cfg_obj=cfg_missing)
    combo_seed, _ = builder.selectors["seed"]
    # Should fall back to the null value
    assert combo_seed.currentIndex() == 0


def test_clear_removes_widgets_and_selectors(builder):
    """`clear()` should delete all widgets and empty the selectors dict."""
    wf_data = make_wf_data([("node", "inp")])
    builder.build_from_api(wf_data, cfg_obj=None)

    # Confirm something is in place before clearing
    assert builder.layout.rowCount() > 0

    assert builder.selectors

    builder.clear()

    # No widgets should remain in the layout
    assert builder.layout.count() == 0
    # Selectors mapping must be empty
    assert not builder.selectors


def test_add_action_buttons_connections(qtbot, builder):
    """
    Verify that the Add/Update and Remove buttons are correctly connected,
    respect the delete‑enable flag, and appear in the layout.
    """

    # Simple counters to record how many times each callback is called
    update_called = {"count": 0}
    delete_called = {"count": 0}

    def dummy_update():
        update_called["count"] += 1

    def dummy_delete():
        delete_called["count"] += 1

    # Add the action buttons to the form builder
    builder.add_action_buttons(dummy_update, dummy_delete, can_delete=False)

    # The layout should now contain one more row for the buttons
    rows = builder.layout.rowCount()
    assert rows >= 1

    # Grab the QHBoxLayout that holds the two buttons.
    item = builder.layout.itemAt(rows - 1, QFormLayout.ItemRole.FieldRole)
    hbox_layout = item.layout()
    assert isinstance(hbox_layout, QHBoxLayout)

    assert hbox_layout.count() == 3
    update_btn = hbox_layout.itemAt(1).widget()
    delete_btn = hbox_layout.itemAt(2).widget()

    assert update_btn.text() == "Add/Update"
    assert delete_btn.text() == "Remove"

    # Delete button should be disabled because can_delete=False
    assert not delete_btn.isEnabled()

    # Click the Update button – the counter should increment once.
    qtbot.mouseClick(update_btn, Qt.MouseButton.LeftButton)
    assert update_called["count"] == 1

    # Clicking a disabled button does nothing; counter stays zero.
    qtbot.mouseClick(delete_btn, Qt.MouseButton.LeftButton)
    assert delete_called["count"] == 0


# --------------------------------------------------------------------------- #
# Edge case: empty workflow data ------------------------------------------ #
def test_build_from_api_empty_data(builder):
    """
    When wf_data contains no nodes, the selectors should still be created but
    only contain the null option.
    """
    builder.build_from_api({}, cfg_obj=None)

    for prop in builder.PROPERTIES:
        combo, options = builder.selectors[prop]
        assert len(options) == 1  # just the null entry
        assert combo.count() == 1
        assert combo.itemText(0) == ""


# --------------------------------------------------------------------------- #
# Edge case: optional properties handling ----------------------------------- #
def test_optional_properties_marked(builder):
    """
    Verify that required vs. optional properties are reflected in the label.
    Optional props get no asterisk; required ones do.
    """
    wf_data = make_wf_data([("node", "inp")])
    builder.build_from_api(wf_data, cfg_obj=None)

    # Gather all QLabel widgets created by the form (excluding hidden ones)
    labels = {lbl.text(): lbl for lbl in builder.parent.findChildren(QLabel)}

    for prop in builder.PROPERTIES:
        required = prop not in builder.OPTIONAL_PROPERTIES
        # Find a label whose text contains the property name
        matching_texts = [txt for txt in labels if prop in txt]
        assert matching_texts, f"Label for {prop} not found"

        # There should be exactly one such label per property
        assert len(matching_texts) == 1, f"Multiple labels for {prop}"
        lbl_text = matching_texts[0]

        if required:
            assert lbl_text.startswith("*"), (
                f"Required prop '{prop}' missing leading '*': {lbl_text}"
            )
        else:
            assert not lbl_text.startswith("*"), (
                f"Optional prop '{prop}' incorrectly has '*': {lbl_text}"
            )
