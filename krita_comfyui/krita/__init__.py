try:
    from krita import (  # ty:ignore[unresolved-import]
        DockWidget,
        DockWidgetFactory,
        DockWidgetFactoryBase,
        Krita,
    )
except Exception:
    import sys
    from unittest.mock import MagicMock

    sys.modules["krita"] = MagicMock()
    from krita import (  # ty:ignore[unresolved-import]
        DockWidget,
        DockWidgetFactory,
        DockWidgetFactoryBase,
        Krita,
    )

__all__ = ["DockWidget", "DockWidgetFactory", "DockWidgetFactoryBase", "Krita"]
