try:
    from krita import DockWidgetFactory, DockWidgetFactoryBase, DockWidget, Krita  # ty:ignore[unresolved-import]
except Exception:
    import sys
    from unittest.mock import MagicMock

    sys.modules["krita"] = MagicMock()
    from krita import DockWidgetFactory, DockWidgetFactoryBase, DockWidget, Krita  # ty:ignore[unresolved-import]

__all__ = ["DockWidgetFactory", "DockWidgetFactoryBase", "DockWidget", "Krita"]
