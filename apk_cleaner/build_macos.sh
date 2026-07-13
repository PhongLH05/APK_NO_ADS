#!/bin/bash
# ═══════════════════════════════════════════════
# build_macos.sh — Đóng gói APK Cleaner thành .app
# Chạy: chmod +x build_macos.sh && ./build_macos.sh
# Kết quả: dist/APK Cleaner.app
# ═══════════════════════════════════════════════

set -e

APP_NAME="APK Cleaner"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║   APK Cleaner — Build macOS Native App       ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# ── 1. Kiểm tra Python ───────────────────────
echo "🔍  Kiểm tra Python..."
if ! command -v python3 &>/dev/null; then
    echo "❌  python3 không tìm thấy!"
    exit 1
fi
PYTHON=$(which python3)
echo "   ✅ $PYTHON"

# ── 2. Cài dependencies ──────────────────────
echo ""
echo "📦  Cài đặt dependencies..."
$PYTHON -m pip install pyinstaller -q 2>/dev/null
echo "   ✅ PyInstaller sẵn sàng"

# ── 3. Clean build cũ ────────────────────────
echo ""
echo "🧹  Dọn build cũ..."
rm -rf build/ dist/ *.spec
echo "   ✅ Sạch"

# ── 4. Build .app ────────────────────────────
echo ""
echo "🔨  Đang build ${APP_NAME}.app ..."
echo ""

# Copy icon vào vị trí
mkdir -p static
if [ -f "static/icon.icns" ]; then
    echo "   ✅ Đã tìm thấy icon.icns"
else
    echo "   ⚠️ Không thấy static/icon.icns, sẽ sử dụng icon mặc định"
fi

$PYTHON -m PyInstaller \
    --name "${APP_NAME}" \
    --windowed \
    --icon "static/icon.icns" \
    --add-data "patterns:patterns" \
    --add-data "tools:tools" \
    --add-data "config.py:." \
    --add-data "decompiler.py:." \
    --add-data "cleaner.py:." \
    --add-data "recompiler.py:." \
    --add-data "logger.py:." \
    --add-data "gui.py:." \
    --hidden-import config \
    --hidden-import decompiler \
    --hidden-import cleaner \
    --hidden-import recompiler \
    --hidden-import logger \
    --hidden-import concurrent.futures \
    --noconfirm \
    --clean \
    app.py

# ── 5. Kiểm tra kết quả ─────────────────────
echo ""
if [ -d "dist/${APP_NAME}.app" ]; then
    SIZE=$(du -sh "dist/${APP_NAME}.app" | cut -f1)
    echo "═══════════════════════════════════════════════"
    echo "✅  BUILD THÀNH CÔNG!"
    echo ""
    echo "   📦  dist/${APP_NAME}.app  (${SIZE})"
    echo ""
    echo "   Cách sử dụng:"
    echo "   1. Kéo thả file 'dist/${APP_NAME}.app' vào thư mục Applications trên Mac."
    echo "   2. Hãy chắc chắn rằng bạn đã đặt apktool.jar"
    echo "      và uber-apk-signer.jar vào thư mục: tools/"
    echo "      (đường dẫn tương đối cùng cấp với file app.py nếu chạy bằng code,"
    echo "       hoặc bỏ trực tiếp vào APK Cleaner.app/Contents/Resources/tools/ nếu chạy app bundle)"
    echo "   3. Double-click để khởi chạy native!"
    echo ""
    echo "   Mở thư mục chứa app:"
    echo "   open dist/"
    echo "═══════════════════════════════════════════════"

    # Mở thư mục dist
    open dist/
else
    echo "❌  Build thất bại! Kiểm tra log ở trên."
    exit 1
fi
