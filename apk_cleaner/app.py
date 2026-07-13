#!/usr/bin/env python3
"""
app.py — APK Cleaner macOS Native Application Launcher
Dùng để chạy trực tiếp app Native Tkinter.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from gui import APKCleanerApp

if __name__ == "__main__":
    app = APKCleanerApp()
    app.mainloop()
