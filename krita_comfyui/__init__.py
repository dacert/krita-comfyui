"""Krita ComfyUI is a lightweight plugin for Krita 5.2+ that lets you run ComfyUI workflows directly from Krita."""

__version__ = "0.2.0"

from .krita import DockWidgetFactory, DockWidgetFactoryBase, Krita
from .krita_comfyui import KritaComfyUi

DOCKER_ID = "krita_comfyui"
instance = Krita.instance()
dock_widget_factory = DockWidgetFactory(DOCKER_ID, DockWidgetFactoryBase.DockRight, KritaComfyUi)

instance.addDockWidgetFactory(dock_widget_factory)
