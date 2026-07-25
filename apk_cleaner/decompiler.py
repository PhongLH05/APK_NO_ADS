"""
decompiler.py — Bước 1: Decompile APK → Smali + XML
Gọi apktool.jar thông qua subprocess để bung file APK ra mã nguồn.
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

import config

logger = logging.getLogger("apk_cleaner")


# ─────────────────────────────────────────────
# Kiểm tra prerequisites
# ─────────────────────────────────────────────
def check_java() -> bool:
    """Kiểm tra Java có sẵn trên PATH không."""
    try:
        result = subprocess.run(
            [config.JAVA_BIN, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # java -version ghi ra stderr
        version_output = result.stderr or result.stdout
        logger.debug(f"Java version: {version_output.strip().splitlines()[0]}")
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def check_jar(jar_path: Path, name: str) -> bool:
    """Kiểm tra file JAR tồn tại."""
    if jar_path.exists():
        logger.debug(f"Tìm thấy {name}: {jar_path}")
        return True
    logger.error(
        f"Không tìm thấy {name} tại: {jar_path}\n"
        f"  → Hãy tải về và đặt vào thư mục: {config.TOOLS_DIR}"
    )
    return False


def download_tools() -> bool:
    """Tự động tải apktool.jar và uber-apk-signer.jar nếu chưa có."""
    import urllib.request
    config.TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    urls = {
        config.APKTOOL_JAR: "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar",
        config.SIGNER_JAR: "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar",
    }

    for jar_path, url in urls.items():
        if not jar_path.exists():
            logger.info(f"Đang tự động tải {jar_path.name}...")
            try:
                urllib.request.urlretrieve(url, jar_path)
                logger.info(f"Tải thành công: {jar_path.name}")
            except Exception as e:
                logger.error(f"Lỗi khi tải {jar_path.name}: {e}")
                return False
    return True


def check_prerequisites() -> bool:
    """
    Kiểm tra toàn bộ prerequisites:
    - Java có trên PATH
    - apktool.jar tồn tại (hoặc tự động tải)
    - uber-apk-signer.jar tồn tại (hoặc tự động tải)

    Returns:
        True nếu tất cả đều hợp lệ, False nếu thiếu.
    """
    logger.info("Kiểm tra prerequisites...")
    ok = True

    if not check_java():
        logger.error(
            "Java không tìm thấy trên hệ thống.\n"
            "  → Tải và cài đặt JDK 8+ từ: https://adoptium.net/\n"
            "  → Sau đó thêm vào PATH và thử lại."
        )
        ok = False
    else:
        logger.info("Java: OK")

    if not config.APKTOOL_JAR.exists() or not config.SIGNER_JAR.exists():
        logger.info("Thiếu file JAR công cụ, đang thử tự động tải...")
        download_tools()

    if not check_jar(config.APKTOOL_JAR, "apktool.jar"):
        logger.error("  → Tải apktool.jar từ: https://ibotpeaches.github.io/Apktool/")
        ok = False
    else:
        logger.info("apktool.jar: OK")

    if not check_jar(config.SIGNER_JAR, "uber-apk-signer.jar"):
        logger.error("  → Tải uber-apk-signer.jar từ: https://github.com/patrickfav/uber-apk-signer/releases")
        ok = False
    else:
        logger.info("uber-apk-signer.jar: OK")

    return ok


def check_apk_integrity(apk_path: Path) -> tuple:
    """Kiểm tra tính toàn vẹn Zip của file APK trước khi decompile."""
    import zipfile
    if not apk_path.exists():
        return False, f"Không tìm thấy file: {apk_path.name}"
    if apk_path.stat().st_size == 0:
        return False, f"File {apk_path.name} rỗng (0 Bytes)."

    try:
        with zipfile.ZipFile(apk_path, 'r') as z:
            bad_file = z.testzip()
            if bad_file:
                return False, f"Dữ liệu file '{bad_file}' bên trong APK bị hỏng."
            return True, "OK"
    except zipfile.BadZipFile:
        return False, f"File '{apk_path.name}' bị thiếu dữ liệu hoặc bị hỏng giữa chừng (Incomplete/Truncated Zip). Vui lòng tải lại file APK."
    except Exception as e:
        return False, f"Lỗi đọc file APK: {e}"


# ─────────────────────────────────────────────
# Decompile APK → Smali
# ─────────────────────────────────────────────
def decompile_apk(apk_path: Path, output_dir: Path) -> bool:
    """
    Dùng apktool để decompile APK thành thư mục chứa Smali + XML.
    """
    apk_path = Path(apk_path)

    if not apk_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file APK: {apk_path}")

    # Kiểm tra toàn vẹn file Zip trước
    valid, reason = check_apk_integrity(apk_path)
    if not valid:
        logger.error(f"❌ File APK không hợp lệ: {reason}")
        return False

    if not apk_path.suffix.lower() == ".apk":
        logger.warning(f"File '{apk_path.name}' không có đuôi .apk — vẫn tiếp tục thử...")

    apk_size_mb = apk_path.stat().st_size / (1024 * 1024)
    logger.info(f"Đang bung file APK: {apk_path.name} ({apk_size_mb:.1f} MB)...")

    # Xóa output cũ nếu tồn tại (flag -f của apktool)
    if output_dir.exists():
        logger.debug(f"Xóa thư mục cũ: {output_dir}")
        shutil.rmtree(output_dir, ignore_errors=True)

    cmd = [
        config.JAVA_BIN, "-jar", str(config.APKTOOL_JAR),
        "d",                    # decompile
        str(apk_path),
        "-o", str(output_dir),
        "-f",                   # force overwrite
    ]

    logger.debug(f"Lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # timeout 5 phút
        )

        if result.returncode != 0:
            logger.error("apktool decompile thất bại!")
            logger.error(f"STDERR:\n{result.stderr}")

            # Gợi ý lỗi thường gặp
            if "brut.androlib.err.UndefinedResObject" in result.stderr:
                logger.warning(
                    "APK có thể dùng resource bị obfuscated. "
                    "Thử thêm flag --no-res để bỏ qua decode resource."
                )
            elif "brut.common.BrutException" in result.stderr:
                logger.warning("APK có thể bị protected chống decompile.")

            return False

        logger.debug(result.stdout)
        logger.info(f"Bung file thành công → {output_dir}")

        # Thống kê nhanh
        smali_count = len(list(output_dir.rglob("*.smali")))
        xml_count   = len(list(output_dir.rglob("*.xml")))
        logger.info(f"Tìm thấy: {smali_count} file .smali, {xml_count} file .xml")

        return True

    except subprocess.TimeoutExpired:
        logger.error("apktool timeout sau 5 phút — APK quá lớn hoặc bị protected.")
        return False
    except Exception as e:
        logger.error(f"Lỗi không mong đợi khi decompile: {e}")
        return False
