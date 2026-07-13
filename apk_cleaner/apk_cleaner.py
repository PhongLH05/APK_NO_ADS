#!/usr/bin/env python3
"""
apk_cleaner.py — Entry point chính của APK Cleaner Tool
Giao diện dòng lệnh (CLI) đầy đủ để tự động hoá quy trình:
  Decompile → Clean → Recompile → Sign

Cách dùng:
  python apk_cleaner.py -i app.apk
  python apk_cleaner.py -i app.apk -o ./output --verbose
  python apk_cleaner.py -i app.apk --keystore my.jks --alias mykey
  python apk_cleaner.py -i app.apk --dry-run
"""

import argparse
import os
import shutil
import sys
from pathlib import Path


# ─────────────────────────────────────────────
# Đảm bảo thư mục hiện tại nằm trong sys.path
# ─────────────────────────────────────────────
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import config
from logger import print_banner, print_report, setup_logger
from decompiler import check_prerequisites, decompile_apk
from cleaner import clean_source_code
from recompiler import recompile_apk, sign_apk


# ─────────────────────────────────────────────
# CLI Argument Parser
# ─────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="apk_cleaner",
        description=(
            "APK Cleaner Tool — Tự động gỡ Ads và chặn Play Store redirect "
            "trong file APK Android."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ sử dụng:
  python apk_cleaner.py -i myapp.apk
  python apk_cleaner.py -i myapp.apk -o ./clean_output --verbose
  python apk_cleaner.py -i myapp.apk --dry-run
  python apk_cleaner.py -i myapp.apk --keystore release.jks --alias mykey
  python apk_cleaner.py -i myapp.apk --patterns my_patterns.json
        """,
    )

    # ── Bắt buộc ────────────────────────────────
    parser.add_argument(
        "-i", "--input",
        required=True,
        metavar="FILE.apk",
        help="Đường dẫn file APK gốc cần xử lý.",
    )

    # ── Tùy chọn đường dẫn ──────────────────────
    parser.add_argument(
        "-o", "--output",
        default=None,
        metavar="DIR",
        help="Thư mục đặt file APK sạch (mặc định: ./output).",
    )
    parser.add_argument(
        "--patterns",
        default=None,
        metavar="FILE.json",
        help="File JSON patterns tùy chỉnh (merge với patterns mặc định).",
    )

    # ── Signing ──────────────────────────────────
    sign_group = parser.add_argument_group("Ký số (Signing)")
    sign_group.add_argument(
        "--keystore",
        default=None,
        metavar="FILE.jks",
        help="Đường dẫn file keystore .jks (bỏ trống để dùng debug key).",
    )
    sign_group.add_argument(
        "--alias",
        default=None,
        metavar="ALIAS",
        help="Alias trong keystore.",
    )
    sign_group.add_argument(
        "--ks-pass",
        default=None,
        metavar="PASSWORD",
        help="Mật khẩu keystore.",
    )

    # ── Behaviour ────────────────────────────────
    behavior_group = parser.add_argument_group("Hành vi")
    behavior_group.add_argument(
        "--keep-temp",
        action="store_true",
        help="Giữ lại thư mục Smali tạm sau khi xong.",
    )
    behavior_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="In log chi tiết (bao gồm cả DEBUG).",
    )
    behavior_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ quét và đếm, không sửa hoặc ghi file nào.",
    )
    behavior_group.add_argument(
        "--no-xml",
        action="store_true",
        help="Bỏ qua bước clean AndroidManifest.xml và layout XML.",
    )

    return parser.parse_args()


# ─────────────────────────────────────────────
# Cleanup thư mục tạm
# ─────────────────────────────────────────────
def cleanup(temp_dir: Path, rebuilt_apk: Path):
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if rebuilt_apk.exists():
            rebuilt_apk.unlink()
    except Exception:
        pass


# ─────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────
def main():
    print_banner()

    args = parse_args()

    # ── Áp dụng args vào config ─────────────────
    config.VERBOSE  = args.verbose
    config.KEEP_TEMP = args.keep_temp
    config.DRY_RUN  = args.dry_run
    config.init_directories()

    # ── Setup logger ────────────────────────────
    logger = setup_logger(config.LOG_DIR, verbose=args.verbose)

    # ── Resolve paths ────────────────────────────
    input_apk   = Path(args.input).resolve()
    output_dir  = Path(args.output).resolve() if args.output else config.OUTPUT_DIR
    temp_dir    = config.TEMP_DIR
    rebuilt_apk = config.REBUILT_APK

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Input APK : {input_apk}")
    logger.info(f"Output dir: {output_dir}")
    if args.dry_run:
        logger.info(">>> CHẾ ĐỘ DRY RUN — không có file nào bị sửa đổi <<<")

    # ────────────────────────────────────────────
    # Bước 0: Kiểm tra prerequisites
    # ────────────────────────────────────────────
    if not check_prerequisites():
        logger.error("Thiếu prerequisite. Vui lòng cài đặt đầy đủ rồi thử lại.")
        sys.exit(1)

    # ────────────────────────────────────────────
    # Bước 1: Decompile
    # ────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("BƯỚC 1/4 — Decompile APK")
    logger.info("=" * 55)

    try:
        ok = decompile_apk(input_apk, temp_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    if not ok:
        logger.error("Decompile thất bại. Dừng lại.")
        sys.exit(1)

    # ────────────────────────────────────────────
    # Bước 2: Clean
    # ────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("BƯỚC 2/4 — Quét & Gỡ Ads + Play Store")
    logger.info("=" * 55)

    report = clean_source_code(
        decompiled_dir       = temp_dir,
        dry_run              = args.dry_run,
        custom_patterns_file = Path(args.patterns) if args.patterns else None,
    )

    if args.dry_run:
        logger.info("Dry run hoàn tất. Không có file nào bị thay đổi.")
        print_report(report, "(dry run — không tạo APK)")
        sys.exit(0)

    # ────────────────────────────────────────────
    # Bước 3: Recompile
    # ────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("BƯỚC 3/4 — Đóng gói lại APK")
    logger.info("=" * 55)

    ok = recompile_apk(temp_dir, rebuilt_apk)
    if not ok:
        logger.error("Recompile thất bại. Kiểm tra log để biết chi tiết.")
        if not args.keep_temp:
            cleanup(temp_dir, rebuilt_apk)
        sys.exit(1)

    # ────────────────────────────────────────────
    # Bước 4: Sign
    # ────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("BƯỚC 4/4 — Ký số APK")
    logger.info("=" * 55)

    signed_apk = sign_apk(
        unsigned_apk    = rebuilt_apk,
        output_dir      = output_dir,
        keystore        = Path(args.keystore) if args.keystore else None,
        keystore_alias  = args.alias,
        keystore_pass   = args.ks_pass,
    )

    if not signed_apk:
        logger.error("Ký số thất bại. APK chưa ký nằm tại: " + str(rebuilt_apk))
        if not args.keep_temp:
            cleanup(temp_dir, rebuilt_apk)
        sys.exit(1)

    # ────────────────────────────────────────────
    # Hoàn thành
    # ────────────────────────────────────────────
    if not args.keep_temp:
        logger.info("Đang dọn dẹp thư mục tạm...")
        cleanup(temp_dir, rebuilt_apk)

    print_report(report, str(signed_apk))

    return 0


if __name__ == "__main__":
    sys.exit(main())
