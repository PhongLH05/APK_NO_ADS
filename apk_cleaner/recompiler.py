"""
recompiler.py — Bước 3 & 4: Recompile APK + Ký số (Sign)
Gọi apktool.jar để đóng gói lại Smali → APK,
rồi gọi uber-apk-signer.jar để ký số tự động.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("apk_cleaner")


# ─────────────────────────────────────────────
# Bước 3: Recompile Smali → APK
# ─────────────────────────────────────────────
def recompile_apk(decompiled_dir: Path, output_apk: Path) -> bool:
    """
    Dùng apktool để đóng gói lại thư mục Smali thành file APK mới.

    Args:
        decompiled_dir: Thư mục chứa mã nguồn đã sửa.
        output_apk:     Đường dẫn file APK đầu ra (chưa ký).

    Returns:
        True nếu thành công, False nếu thất bại.
    """
    decompiled_dir = Path(decompiled_dir)
    output_apk     = Path(output_apk)

    if not decompiled_dir.exists():
        logger.error(f"Không tìm thấy thư mục source: {decompiled_dir}")
        return False

    output_apk.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Đang đóng gói lại APK từ: {decompiled_dir}...")

    cmd = [
        config.JAVA_BIN, "-jar", str(config.APKTOOL_JAR),
        "b",                        # build
        str(decompiled_dir),
        "-o", str(output_apk),
    ]

    logger.debug(f"Lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 phút
        )

        if result.returncode != 0:
            logger.error("apktool recompile thất bại!")
            logger.error(f"STDERR:\n{result.stderr}")

            # Gợi ý lỗi thường gặp
            stderr = result.stderr
            if "aapt" in stderr or "resource" in stderr.lower():
                logger.warning(
                    "Lỗi resource. Thử thêm --use-aapt2 hoặc kiểm tra "
                    "file AndroidManifest.xml đã được comment đúng chưa."
                )
            elif "brut.androlib" in stderr:
                logger.warning("Lỗi rebuild nội bộ của apktool. Kiểm tra log chi tiết.")

            return False

        logger.debug(result.stdout)
        logger.info(f"Đóng gói thành công → {output_apk}")
        return True

    except subprocess.TimeoutExpired:
        logger.error("apktool timeout sau 10 phút khi recompile.")
        return False
    except Exception as e:
        logger.error(f"Lỗi không mong đợi khi recompile: {e}")
        return False


# ─────────────────────────────────────────────
# Bước 4: Sign APK
# ─────────────────────────────────────────────
def sign_apk(
    unsigned_apk: Path,
    output_dir: Path,
    keystore: Optional[Path] = None,
    keystore_alias: Optional[str] = None,
    keystore_pass: Optional[str] = None,
) -> Optional[Path]:
    """
    Ký số APK bằng Uber-APK-Signer.

    Args:
        unsigned_apk:   File APK chưa ký.
        output_dir:     Thư mục đặt file đã ký.
        keystore:       Đường dẫn file .jks (None → dùng debug key tự động).
        keystore_alias: Alias trong keystore.
        keystore_pass:  Mật khẩu keystore.

    Returns:
        Path file APK đã ký nếu thành công, None nếu thất bại.
    """
    unsigned_apk = Path(unsigned_apk)
    output_dir   = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not unsigned_apk.exists():
        logger.error(f"Không tìm thấy APK chưa ký: {unsigned_apk}")
        return None

    mode = "production keystore" if keystore else "debug key (tự động)"
    logger.info(f"Đang ký số APK ({mode})...")

    cmd = [
        config.JAVA_BIN, "-jar", str(config.SIGNER_JAR),
        "--apks", str(unsigned_apk),
        "--out",  str(output_dir),
    ]

    # Thêm keystore tùy chỉnh nếu có
    if keystore:
        keystore = Path(keystore)
        if not keystore.exists():
            logger.error(f"Không tìm thấy file keystore: {keystore}")
            return None
        cmd.extend(["--ks", str(keystore)])
        if keystore_alias:
            cmd.extend(["--ksAlias", keystore_alias])
        if keystore_pass:
            cmd.extend(["--ksPass", keystore_pass])

    logger.debug(f"Lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 phút
        )

        if result.returncode != 0:
            logger.error("Ký số APK thất bại!")
            logger.error(f"STDERR:\n{result.stderr}")

            if "could not find" in result.stderr.lower():
                logger.warning("Uber-APK-Signer không tìm thấy APK. Kiểm tra đường dẫn.")
            elif "keystore" in result.stderr.lower():
                logger.warning("Lỗi keystore. Kiểm tra alias và mật khẩu.")

            return None

        logger.debug(result.stdout)

        # Uber-APK-Signer đặt tên file output theo format: <name>-aligned-signed.apk
        stem   = unsigned_apk.stem
        signed = list(output_dir.glob(f"{stem}*signed*.apk"))
        if not signed:
            # Fallback: lấy file APK mới nhất trong output_dir
            signed = sorted(output_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)

        if signed:
            logger.info(f"Ký số thành công → {signed[0]}")
            return signed[0]
        else:
            logger.warning(f"Ký số xong nhưng không tìm thấy file APK trong: {output_dir}")
            return None

    except subprocess.TimeoutExpired:
        logger.error("Uber-APK-Signer timeout sau 2 phút.")
        return None
    except Exception as e:
        logger.error(f"Lỗi không mong đợi khi ký số: {e}")
        return None
