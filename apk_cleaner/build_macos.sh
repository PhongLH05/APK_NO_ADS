#!/bin/bash
# ═══════════════════════════════════════════════
# build_macos.sh — Đóng gói APK Cleaner thành .app Native macOS
# Đã chuyển sang Swift Native App Engine (WKWebView)
# Dễ dùng, cực đẹp, 100% không bị lỗi màn hình đen của Tcl/Tk cũ.
# ═══════════════════════════════════════════════

set -e

APP_NAME="APK Cleaner"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║   APK Cleaner — Build macOS Native App (Swift) ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# ── 1. Clean old build ───────────────────────
echo "🧹  Dọn dẹp build cũ..."
rm -rf "dist/${APP_NAME}.app"
mkdir -p "dist/${APP_NAME}.app/Contents/MacOS"
mkdir -p "dist/${APP_NAME}.app/Contents/Resources"

# ── 2. Biên dịch Swift Native App Launcher ───
echo ""
echo "⚙️  Biên dịch Swift Native App Engine..."
swiftc -O main.swift -o "dist/${APP_NAME}.app/Contents/MacOS/${APP_NAME}"
echo "   ✅ Native macOS App Binary compiled"

# ── 3. Copy Resources ────────────────────────
echo ""
echo "📦  Đóng gói tài nguyên và mã nguồn..."
cp -R static "dist/${APP_NAME}.app/Contents/Resources/"
cp -R tools "dist/${APP_NAME}.app/Contents/Resources/"
cp -R patterns "dist/${APP_NAME}.app/Contents/Resources/"
cp config.py "dist/${APP_NAME}.app/Contents/Resources/"
cp decompiler.py "dist/${APP_NAME}.app/Contents/Resources/"
cp cleaner.py "dist/${APP_NAME}.app/Contents/Resources/"
cp recompiler.py "dist/${APP_NAME}.app/Contents/Resources/"
cp logger.py "dist/${APP_NAME}.app/Contents/Resources/"
cp gui.py "dist/${APP_NAME}.app/Contents/Resources/"

if [ -f "static/icon.icns" ]; then
    cp static/icon.icns "dist/${APP_NAME}.app/Contents/Resources/icon.icns"
fi
echo "   ✅ Tài nguyên hoàn tất"

# ── 4. Tạo file Info.plist chuẩn macOS ────────
echo ""
echo "📄  Tạo file Info.plist..."
cat <<EOF > "dist/${APP_NAME}.app/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.phonglh.apkcleaner</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>3.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

echo ""
SIZE=$(du -sh "dist/${APP_NAME}.app" | cut -f1)
echo "═══════════════════════════════════════════════"
echo "✅  BUILD THÀNH CÔNG!"
echo ""
echo "   📦  dist/${APP_NAME}.app  (${SIZE})"
echo ""
echo "   Cách sử dụng:"
echo "   1. Kéo thả file 'dist/${APP_NAME}.app' vào thư mục /Applications/"
echo "   2. Double-click để khởi chạy Native trên Mac!"
echo "═══════════════════════════════════════════════"

open dist/
