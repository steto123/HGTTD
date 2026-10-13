import sys
import os

# Add script directory to path for embeddable python
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Suppress noisy internal Chromium GPU mailbox and diagnostic logs
existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (existing_flags + " --log-level=3 --disable-logging").strip()
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false;qt.text.*=false"

import ctypes
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from ketcher_server import KetcherServer
from main_window import ModernMainWindow

def main():
    # Set current directory to directory of app.py
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Start Ketcher server (standalone is under 'ketcher/standalone')
    ketcher_dir = os.path.join("ketcher", "standalone")
    if not os.path.exists(os.path.join(ketcher_dir, "index.html")):
        # If it doesn't exist, check standard ketcher path
        ketcher_dir = "ketcher"

    server = KetcherServer(directory=ketcher_dir)
    server.start()
    
    # Initialize Qt with High-DPI support across monitors with different scales
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("HGTTD")
    
    # Windows Taskbar AppUserModelID so taskbar displays custom icon properly
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HGTTD.SpectraGuide.App.2026")
        except Exception:
            pass

    # Set Application Icon
    icon_ico = os.path.join(script_dir, "assets", "hgttd_icon.ico")
    icon_png = os.path.join(script_dir, "assets", "hgttd_icon.png")
    app_icon = QIcon(icon_ico if os.path.exists(icon_ico) else icon_png)
    app.setWindowIcon(app_icon)

    # Set explicit valid application font with positive point size
    default_font = QFont("Segoe UI", 10)
    default_font.setPointSize(10)
    app.setFont(default_font)
    
    # Create Main Window
    window = ModernMainWindow(server.get_url())
    window.setWindowIcon(app_icon)
    window.show()
    
    # Run loop
    exit_code = app.exec()
    
    # Stop Server
    server.stop()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
