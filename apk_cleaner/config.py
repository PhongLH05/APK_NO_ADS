"""
config.py — Cấu hình tập trung cho APK Cleaner Tool
Chỉnh sửa file này để cấu hình đường dẫn công cụ và các tham số mặc định.
"""

import os
from pathlib import Path

# ─────────────────────────────────────────────
# Thư mục gốc của project
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# ─────────────────────────────────────────────
# Đường dẫn công cụ Java/JAR
# Tool tự động tìm trong thư mục "tools/" trước,
# sau đó fallback sang PATH hệ thống.
# ─────────────────────────────────────────────
TOOLS_DIR       = BASE_DIR / "tools"
APKTOOL_JAR     = TOOLS_DIR / "apktool.jar"
SIGNER_JAR      = TOOLS_DIR / "uber-apk-signer.jar"
JAVA_BIN        = "java"   # override bằng full path nếu cần, vd: "/usr/lib/jvm/java-17/bin/java"

# ─────────────────────────────────────────────
# Thư mục làm việc (workspace)
# ─────────────────────────────────────────────
WORKSPACE_DIR   = BASE_DIR / "workspace"
TEMP_DIR        = WORKSPACE_DIR / "extracted"
REBUILT_APK     = WORKSPACE_DIR / "modified_unsigned.apk"

# ─────────────────────────────────────────────
# Thư mục output & log
# ─────────────────────────────────────────────
OUTPUT_DIR      = BASE_DIR / "output"
LOG_DIR         = BASE_DIR / "logs"

# ─────────────────────────────────────────────
# Đường dẫn file patterns
# ─────────────────────────────────────────────
PATTERNS_DIR        = BASE_DIR / "patterns"
ADS_PATTERNS_FILE   = PATTERNS_DIR / "ads_patterns.json"
STORE_PATTERNS_FILE = PATTERNS_DIR / "store_patterns.json"

# ─────────────────────────────────────────────
# Cờ hành vi mặc định
# ─────────────────────────────────────────────
KEEP_TEMP           = False     # Giữ thư mục tạm sau khi xong
VERBOSE             = False     # In log chi tiết
DRY_RUN             = False     # Chỉ quét, không ghi file
MAX_THREAD_WORKERS  = 4         # Số luồng tối đa khi xử lý đa luồng
MULTITHREAD_THRESHOLD_MB = 20   # APK lớn hơn ngưỡng này mới dùng đa luồng

# ─────────────────────────────────────────────
# Marker nhận diện file đã được clean
# ─────────────────────────────────────────────
CLEANED_MARKER      = "# [APK_CLEANER] blocked"

# ─────────────────────────────────────────────
# Tạo các thư mục cần thiết nếu chưa tồn tại
# ─────────────────────────────────────────────
def init_directories():
    for d in [WORKSPACE_DIR, TEMP_DIR, OUTPUT_DIR, LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)
