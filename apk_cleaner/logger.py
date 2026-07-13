"""
logger.py — Hệ thống logging màu sắc cho APK Cleaner Tool
Hỗ trợ ghi log ra file và in màu ra terminal (không cần thư viện ngoài).
"""

import logging
import sys
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
# ANSI Color Codes (hoạt động trên Mac/Linux/Windows 10+)
# ─────────────────────────────────────────────
class Colors:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    DIM     = "\033[2m"


# ─────────────────────────────────────────────
# Custom Formatter: in màu ra terminal
# ─────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG:    Colors.DIM    + "[DEBUG]"   + Colors.RESET,
        logging.INFO:     Colors.CYAN   + "[INFO] "   + Colors.RESET,
        logging.WARNING:  Colors.YELLOW + "[WARN] "   + Colors.RESET,
        logging.ERROR:    Colors.RED    + "[ERROR]"   + Colors.RESET,
        logging.CRITICAL: Colors.RED    + Colors.BOLD + "[CRIT] " + Colors.RESET,
    }

    ICONS = {
        logging.DEBUG:    "  ",
        logging.INFO:     "✔ ",
        logging.WARNING:  "⚠ ",
        logging.ERROR:    "✘ ",
        logging.CRITICAL: "💀",
    }

    def format(self, record: logging.LogRecord) -> str:
        level_str = self.LEVEL_COLORS.get(record.levelno, "[????]")
        icon       = self.ICONS.get(record.levelno, "  ")
        time_str   = Colors.DIM + datetime.now().strftime("%H:%M:%S") + Colors.RESET
        msg        = record.getMessage()
        return f"{time_str}  {level_str}  {icon}{msg}"


# ─────────────────────────────────────────────
# Plain Formatter: ghi vào file (không có ANSI)
# ─────────────────────────────────────────────
class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        level_names = {
            logging.DEBUG:    "DEBUG   ",
            logging.INFO:     "INFO    ",
            logging.WARNING:  "WARNING ",
            logging.ERROR:    "ERROR   ",
            logging.CRITICAL: "CRITICAL",
        }
        level_str = level_names.get(record.levelno, "UNKNOWN ")
        time_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{time_str}  {level_str}  {record.getMessage()}"


# ─────────────────────────────────────────────
# Factory: tạo và cấu hình logger
# ─────────────────────────────────────────────
def setup_logger(log_dir: Path, verbose: bool = False) -> logging.Logger:
    """
    Tạo logger ghi đồng thời ra:
    - Terminal (có màu)
    - File log trong log_dir (plain text)

    Args:
        log_dir:  Thư mục lưu file log.
        verbose:  True → hiện DEBUG, False → hiện INFO trở lên.

    Returns:
        logging.Logger đã cấu hình.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = log_dir / f"run_{timestamp}.log"

    logger = logging.getLogger("apk_cleaner")
    logger.setLevel(logging.DEBUG)  # bắt tất cả, handler tự filter

    # ── Handler 1: Terminal ──────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(ColorFormatter())
    logger.addHandler(console_handler)

    # ── Handler 2: File ──────────────────────
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(PlainFormatter())
    logger.addHandler(file_handler)

    logger.info(f"Log file: {log_file}")
    return logger


# ─────────────────────────────────────────────
# Helper: in banner đẹp khi khởi động
# ─────────────────────────────────────────────
def print_banner():
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
  ╔══════════════════════════════════════════════╗
  ║          APK CLEANER TOOL  v1.0              ║
  ║   Gỡ Ads + Chặn Play Store tự động          ║
  ╚══════════════════════════════════════════════╝
{Colors.RESET}"""
    print(banner)


# ─────────────────────────────────────────────
# Helper: in báo cáo tổng kết cuối pipeline
# ─────────────────────────────────────────────
def print_report(report: dict, output_apk: str):
    sep = Colors.DIM + "─" * 50 + Colors.RESET
    print(f"\n{sep}")
    print(f"{Colors.BOLD}{Colors.GREEN}  📊  KẾT QUẢ XỬ LÝ{Colors.RESET}")
    print(sep)
    print(f"  📁  Files đã quét        : {Colors.WHITE}{report.get('files_scanned', 0)}{Colors.RESET}")
    print(f"  ✏️   Files đã sửa         : {Colors.YELLOW}{report.get('files_modified', 0)}{Colors.RESET}")
    print(f"  🚫  Ads methods bị block  : {Colors.RED}{report.get('ads_methods_blocked', 0)}{Colors.RESET}")
    print(f"  🔗  Play Store bị chặn   : {Colors.RED}{report.get('store_redirects_blocked', 0)}{Colors.RESET}")
    print(f"  🗑️   XML entries đã xoá   : {Colors.RED}{report.get('xml_entries_removed', 0)}{Colors.RESET}")
    print(sep)
    print(f"  ✅  OUTPUT: {Colors.GREEN}{Colors.BOLD}{output_apk}{Colors.RESET}")
    print(f"{sep}\n")
