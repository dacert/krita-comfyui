"""
Minimal pytest configuration.

Forces the ``offscreen`` Qt platform plugin when running tests in
headless environments (e.g. CI). This avoids the ``xcb`` plugin
crash on systems without a display server.
"""

import os

# Set the Qt platform BEFORE any PyQt5 import so pytest-qt's qapp
# fixture can create a QApplication without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")