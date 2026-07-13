"""
cleaner.py — Bước 2: Quét và sửa mã nguồn Smali + XML
Module trọng tâm: phân tích từng method trong Smali, inject early-return
để vô hiệu hoá quảng cáo và chặn điều hướng Play Store.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("apk_cleaner")


# ─────────────────────────────────────────────
# Data Classes đơn giản (không cần dataclasses)
# ─────────────────────────────────────────────
class SmaliMethod:
    """Đại diện cho một method block trong file Smali."""

    def __init__(
        self,
        signature: str,
        body_lines: list[str],
        start_line: int,
        end_line: int,
        return_type: str,
    ):
        self.signature   = signature    # vd: "public loadAd(Lcom/google/android/gms/ads/AdRequest;)V"
        self.body_lines  = body_lines   # các dòng bên trong .method … .end method
        self.start_line  = start_line   # index dòng bắt đầu (0-indexed) trong toàn file
        self.end_line    = end_line     # index dòng kết thúc
        self.return_type = return_type  # "V", "Z", "I", "L...", "[..."


# ─────────────────────────────────────────────
# Bước 2a: Smali Method Parser
# ─────────────────────────────────────────────
class SmaliMethodParser:
    """Tách từng .method … .end method block thành SmaliMethod object."""

    # Ví dụ signature: ".method public final loadAd(Lcom/google/android/gms/ads/AdRequest;)V"
    METHOD_START_RE = re.compile(r"^\.method\s+(.+)$")
    METHOD_END      = ".end method"

    @staticmethod
    def _extract_return_type(signature: str) -> str:
        """
        Lấy kiểu trả về từ signature Smali.
        Ví dụ: "loadAd(Lcom/.../AdRequest;)V" → "V"
                "getFlag()Z"                   → "Z"
                "getObject()Ljava/lang/Object;" → "L"
                "getArray()[B"                 → "["
        """
        # Tìm phần sau dấu )
        match = re.search(r"\)(.+)$", signature.strip())
        if not match:
            return "V"
        ret = match.group(1).strip()
        if ret == "V":
            return "V"
        if ret.startswith("["):
            return "["
        if ret.startswith("L"):
            return "L"
        return ret  # I, Z, B, S, F, D, J, C

    @classmethod
    def parse(cls, lines: list[str]) -> list[SmaliMethod]:
        """
        Parse toàn bộ dòng của 1 file Smali.
        Trả về list SmaliMethod.
        """
        methods: list[SmaliMethod] = []
        i = 0
        depth = 0  # hỗ trợ method lồng (hiếm nhưng có)

        while i < len(lines):
            line = lines[i]
            m = cls.METHOD_START_RE.match(line.strip())

            if m:
                depth += 1
                if depth == 1:
                    start_line = i
                    sig_full   = m.group(1)
                    body       = [line]
                    i += 1
                    # Thu thập body cho đến .end method
                    while i < len(lines):
                        body.append(lines[i])
                        if lines[i].strip() == cls.METHOD_END:
                            depth -= 1
                            if depth == 0:
                                break
                        elif cls.METHOD_START_RE.match(lines[i].strip()):
                            depth += 1
                        i += 1

                    end_line    = i
                    return_type = cls._extract_return_type(sig_full)
                    methods.append(
                        SmaliMethod(
                            signature   = sig_full,
                            body_lines  = body,
                            start_line  = start_line,
                            end_line    = end_line,
                            return_type = return_type,
                        )
                    )
            i += 1

        return methods


# ─────────────────────────────────────────────
# Bước 2b: Ads Blocker
# ─────────────────────────────────────────────
class AdsBlocker:
    """Vô hiệu hoá các method quảng cáo bằng cách inject early-return."""

    def __init__(self, patterns: dict):
        self.sdk_packages  = patterns.get("sdk_packages", [])
        self.method_names  = patterns.get("method_names", [])
        self.class_keywords = patterns.get("class_keywords", [])

    def _build_early_return(self, return_type: str) -> list[str]:
        """
        Tạo đoạn code Smali để kết thúc method ngay lập tức.
        Luôn bảo toàn .registers directive nếu có.
        """
        marker = f"    {config.CLEANED_MARKER}"
        if return_type == "V":
            return [marker, "    return-void"]
        elif return_type == "Z":
            return [marker, "    const/4 v0, 0x0", "    return v0"]
        elif return_type in ("I", "B", "S", "C"):
            return [marker, "    const/4 v0, 0x0", "    return v0"]
        elif return_type == "F":
            return [marker, "    const/4 v0, 0x0", "    return v0"]
        elif return_type in ("D", "J"):
            return [marker, "    const-wide/16 v0, 0x0", "    return-wide v0"]
        elif return_type in ("L", "["):
            return [marker, "    const/4 v0, 0x0", "    return-object v0"]
        else:
            return [marker, "    return-void"]

    def _is_ads_related(self, method: SmaliMethod, file_content: str) -> bool:
        """
        Kiểm tra method có liên quan đến Ads SDK không.
        Kết hợp 3 tín hiệu: tên method, nội dung method, nội dung file.
        """
        body_str = "\n".join(method.body_lines)

        # Tín hiệu 1: method name khớp với danh sách đã biết
        for mname in self.method_names:
            if mname.lower() in method.signature.lower():
                # Xác nhận thêm: file có chứa SDK package không?
                for pkg in self.sdk_packages:
                    if pkg in file_content:
                        return True

        # Tín hiệu 2: body method tham chiếu trực tiếp đến SDK package
        for pkg in self.sdk_packages:
            if pkg in body_str:
                return True

        return False

    def _already_blocked(self, method: SmaliMethod) -> bool:
        """Kiểm tra method đã bị block bởi lần chạy trước chưa."""
        for line in method.body_lines[:5]:
            if config.CLEANED_MARKER in line:
                return True
        return False

    def _inject_into_method(self, method: SmaliMethod) -> list[str]:
        """
        Inject early-return vào ngay sau dòng .method (và .registers nếu có).
        Trả về body_lines mới.
        """
        new_lines = []
        inserted  = False

        for idx, line in enumerate(method.body_lines):
            new_lines.append(line)
            stripped = line.strip()

            # Bỏ qua dòng đầu tiên (.method ...) và .registers ...
            if idx == 0:
                continue
            if stripped.startswith(".registers") or stripped.startswith(".locals"):
                if not inserted:
                    new_lines.extend(self._build_early_return(method.return_type))
                    inserted = True
                continue
            if not inserted and stripped and not stripped.startswith("#"):
                # Chèn trước dòng code đầu tiên thực sự
                new_lines = new_lines[:-1]  # bỏ dòng vừa thêm
                new_lines.extend(self._build_early_return(method.return_type))
                new_lines.append(line)
                inserted = True

        return new_lines

    def process_file(
        self,
        file_path: Path,
        dry_run: bool = False,
    ) -> int:
        """
        Xử lý 1 file .smali, trả về số method đã bị block.
        """
        try:
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = file_path.read_text(encoding="latin-1")

            lines   = content.splitlines(keepends=True)
            methods = SmaliMethodParser.parse(lines)

            if not methods:
                return 0

            blocked = 0
            # Duyệt ngược để offset không bị lệch khi chèn dòng
            for method in reversed(methods):
                if self._already_blocked(method):
                    continue
                if self._is_ads_related(method, content):
                    new_body = self._inject_into_method(method)
                    lines[method.start_line : method.end_line + 1] = new_body
                    blocked += 1
                    logger.debug(
                        f"  Blocked ads method: {method.signature[:60]}... "
                        f"(return type: {method.return_type})"
                    )

            if blocked > 0 and not dry_run:
                file_path.write_text("".join(lines), encoding="utf-8")

            return blocked

        except Exception as e:
            logger.warning(f"Lỗi xử lý {file_path.name}: {e}")
            return 0


# ─────────────────────────────────────────────
# Bước 2c: Play Store Redirect Blocker
# ─────────────────────────────────────────────
class StoreRedirectBlocker:
    """Chặn các method điều hướng người dùng đến Play Store."""

    def __init__(self, patterns: dict):
        self.uri_patterns       = patterns.get("uri_patterns", [])
        self.rate_us_keywords   = patterns.get("rate_us_keywords", [])

    def _method_has_store_redirect(self, method: SmaliMethod) -> bool:
        body_str = "\n".join(method.body_lines)

        # Kiểm tra URI pattern
        for pattern in self.uri_patterns:
            try:
                if re.search(pattern, body_str):
                    return True
            except re.error:
                if pattern in body_str:
                    return True

        # Kiểm tra rate-us keyword
        for keyword in self.rate_us_keywords:
            try:
                if re.search(keyword, body_str, re.IGNORECASE):
                    return True
            except re.error:
                if keyword.lower() in body_str.lower():
                    return True

        return False

    def _already_blocked(self, method: SmaliMethod) -> bool:
        for line in method.body_lines[:5]:
            if config.CLEANED_MARKER in line:
                return True
        return False

    def _inject_early_return(self, method: SmaliMethod) -> list[str]:
        """Chèn return-void vào đầu method (hầu hết là void)."""
        new_lines = []
        inserted  = False
        marker    = f"    {config.CLEANED_MARKER} (store_redirect)"
        ret_type  = method.return_type

        for idx, line in enumerate(method.body_lines):
            new_lines.append(line)
            stripped = line.strip()

            if idx == 0:
                continue
            if stripped.startswith(".registers") or stripped.startswith(".locals"):
                if not inserted:
                    if ret_type == "V":
                        new_lines.extend([marker, "    return-void"])
                    elif ret_type in ("Z", "I", "B", "S", "C", "F"):
                        new_lines.extend([marker, "    const/4 v0, 0x0", "    return v0"])
                    else:
                        new_lines.extend([marker, "    return-void"])
                    inserted = True
                continue
            if not inserted and stripped and not stripped.startswith("#"):
                new_lines = new_lines[:-1]
                if ret_type == "V":
                    new_lines.extend([marker, "    return-void"])
                elif ret_type in ("Z", "I", "B", "S", "C", "F"):
                    new_lines.extend([marker, "    const/4 v0, 0x0", "    return v0"])
                else:
                    new_lines.extend([marker, "    return-void"])
                new_lines.append(line)
                inserted = True

        return new_lines

    def process_file(self, file_path: Path, dry_run: bool = False) -> int:
        try:
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = file_path.read_text(encoding="latin-1")

            # Quick check trước khi parse toàn bộ
            has_store_ref = any(
                re.search(p, content) for p in self.uri_patterns
            ) or any(
                kw.lower() in content.lower() for kw in self.rate_us_keywords
            )

            if not has_store_ref:
                return 0

            lines   = content.splitlines(keepends=True)
            methods = SmaliMethodParser.parse(lines)
            blocked = 0

            for method in reversed(methods):
                if self._already_blocked(method):
                    continue
                if self._method_has_store_redirect(method):
                    new_body = self._inject_early_return(method)
                    lines[method.start_line : method.end_line + 1] = new_body
                    blocked += 1
                    logger.debug(
                        f"  Blocked store redirect in: {method.signature[:60]}..."
                    )

            if blocked > 0 and not dry_run:
                file_path.write_text("".join(lines), encoding="utf-8")

            return blocked

        except Exception as e:
            logger.warning(f"Lỗi xử lý store redirect tại {file_path.name}: {e}")
            return 0


# ─────────────────────────────────────────────
# Bước 2d: XML Cleaner
# ─────────────────────────────────────────────
class XMLCleaner:
    """
    Gỡ khai báo quảng cáo trong AndroidManifest.xml và layout XML.
    Chiến lược: comment out thay vì xóa → APKTool vẫn compile được.
    """

    def __init__(self, sdk_packages: list[str]):
        self.sdk_packages = sdk_packages
        # Chuyển package path thành package name (dấu / → .)
        self.sdk_names = [p.replace("/", ".") for p in sdk_packages]

    def _should_comment_line(self, line: str) -> bool:
        for name in self.sdk_names:
            if name in line:
                return True
        # Thêm class keyword của AdView
        for keyword in ["AdView", "AdMob", "AdBanner", "AdContainer"]:
            if keyword in line:
                return True
        return False

    def clean_manifest(self, manifest_path: Path, dry_run: bool = False) -> int:
        """
        Comment out các activity/service/receiver/meta-data liên quan đến Ads SDK.
        Trả về số dòng bị comment.
        """
        if not manifest_path.exists():
            return 0

        try:
            content = manifest_path.read_text(encoding="utf-8")
            lines   = content.splitlines(keepends=True)
            removed = 0
            new_lines = []
            skip_block = False

            for line in lines:
                stripped = line.strip()

                # Bắt đầu block tag liên quan đến Ads
                if not skip_block and self._should_comment_line(line):
                    skip_block = True
                    removed += 1
                    new_lines.append(
                        f"<!-- [APK_CLEANER] {line.rstrip()} -->\n"
                    )
                    continue

                if skip_block:
                    new_lines.append(f"<!-- [APK_CLEANER] {line.rstrip()} -->\n")
                    removed += 1
                    # Kết thúc block khi gặp tag đóng
                    if "/>" in stripped or "</" in stripped:
                        skip_block = False
                    continue

                new_lines.append(line)

            if removed > 0 and not dry_run:
                manifest_path.write_text("".join(new_lines), encoding="utf-8")

            return removed

        except Exception as e:
            logger.warning(f"Lỗi xử lý AndroidManifest.xml: {e}")
            return 0

    def clean_layout_xmls(self, res_dir: Path, dry_run: bool = False) -> int:
        """
        Duyệt qua các file layout XML, comment out AdView widgets.
        Trả về tổng số entries đã xóa.
        """
        if not res_dir.exists():
            return 0

        total = 0
        layout_dir = res_dir / "layout"
        if not layout_dir.exists():
            return 0

        for xml_file in layout_dir.rglob("*.xml"):
            try:
                content = xml_file.read_text(encoding="utf-8")
                if not any(kw in content for kw in ["AdView", "AdMob"] + self.sdk_names[:5]):
                    continue

                lines     = content.splitlines(keepends=True)
                new_lines = []
                skip_block = False
                removed    = 0

                for line in lines:
                    if not skip_block and self._should_comment_line(line):
                        skip_block = True
                        removed += 1
                        new_lines.append(f"<!-- [APK_CLEANER] {line.rstrip()} -->\n")
                        continue
                    if skip_block:
                        new_lines.append(f"<!-- [APK_CLEANER] {line.rstrip()} -->\n")
                        removed += 1
                        if "/>" in line.strip() or "</" in line.strip():
                            skip_block = False
                        continue
                    new_lines.append(line)

                if removed > 0:
                    total += removed
                    if not dry_run:
                        xml_file.write_text("".join(new_lines), encoding="utf-8")
                    logger.debug(f"  XML cleaned: {xml_file.name} ({removed} entries)")

            except Exception as e:
                logger.warning(f"Lỗi xử lý layout XML {xml_file.name}: {e}")

        return total


# ─────────────────────────────────────────────
# Tải patterns từ JSON
# ─────────────────────────────────────────────
def load_patterns() -> tuple[dict, dict]:
    """Tải ads_patterns.json và store_patterns.json."""
    try:
        ads_patterns = json.loads(config.ADS_PATTERNS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Không đọc được ads_patterns.json: {e}")
        ads_patterns = {}

    try:
        store_patterns = json.loads(config.STORE_PATTERNS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Không đọc được store_patterns.json: {e}")
        store_patterns = {}

    return ads_patterns, store_patterns


# ─────────────────────────────────────────────
# Điều phối tổng — clean_source_code
# ─────────────────────────────────────────────
def clean_source_code(
    decompiled_dir: Path,
    dry_run: bool = False,
    custom_patterns_file: Optional[Path] = None,
) -> dict:
    """
    Pipeline cleaning hoàn chỉnh:
    1. Tải patterns
    2. Quét tất cả .smali → block ads methods + store redirects
    3. Clean AndroidManifest.xml
    4. Clean layout XMLs

    Args:
        decompiled_dir:        Thư mục đã decompile (output của apktool).
        dry_run:               True → chỉ đếm, không ghi file.
        custom_patterns_file:  File JSON patterns tùy chỉnh (optional).

    Returns:
        dict với thống kê xử lý.
    """
    decompiled_dir = Path(decompiled_dir)

    # Tải patterns
    ads_patterns, store_patterns = load_patterns()

    # Merge patterns tùy chỉnh nếu có
    if custom_patterns_file and Path(custom_patterns_file).exists():
        try:
            custom = json.loads(Path(custom_patterns_file).read_text(encoding="utf-8"))
            if "sdk_packages" in custom:
                ads_patterns["sdk_packages"] = list(
                    set(ads_patterns.get("sdk_packages", []) + custom["sdk_packages"])
                )
            logger.info(f"Đã tải patterns tùy chỉnh: {custom_patterns_file}")
        except Exception as e:
            logger.warning(f"Không đọc được custom patterns: {e}")

    ads_blocker   = AdsBlocker(ads_patterns)
    store_blocker = StoreRedirectBlocker(store_patterns)
    xml_cleaner   = XMLCleaner(ads_patterns.get("sdk_packages", []))

    # Thu thập tất cả file .smali
    smali_files = list(decompiled_dir.rglob("*.smali"))
    total_files = len(smali_files)
    logger.info(f"Bắt đầu quét {total_files} file Smali...")

    if dry_run:
        logger.info("[DRY RUN] Chỉ đếm, không ghi file.")

    # ── Quyết định đa luồng hay đơn luồng ───────
    apk_size_mb  = sum(f.stat().st_size for f in smali_files) / (1024 * 1024)
    use_threads  = apk_size_mb >= config.MULTITHREAD_THRESHOLD_MB
    max_workers  = min(config.MAX_THREAD_WORKERS, os.cpu_count() or 2)

    logger.info(
        f"Tổng kích thước Smali: {apk_size_mb:.1f} MB → "
        f"{'Đa luồng (' + str(max_workers) + ' workers)' if use_threads else 'Đơn luồng'}"
    )

    total_ads_blocked   = 0
    total_store_blocked = 0
    files_modified      = 0

    def process_single_file(f: Path) -> tuple[int, int]:
        ads   = ads_blocker.process_file(f, dry_run=dry_run)
        store = store_blocker.process_file(f, dry_run=dry_run)
        return ads, store

    if use_threads:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_single_file, f): f for f in smali_files}
            done = 0
            for future in as_completed(futures):
                ads, store = future.result()
                total_ads_blocked   += ads
                total_store_blocked += store
                if ads + store > 0:
                    files_modified += 1
                done += 1
                if done % 100 == 0 or done == total_files:
                    logger.info(f"  Tiến độ: {done}/{total_files} files...")
    else:
        for i, f in enumerate(smali_files, 1):
            ads, store = process_single_file(f)
            total_ads_blocked   += ads
            total_store_blocked += store
            if ads + store > 0:
                files_modified += 1
            if i % 100 == 0 or i == total_files:
                logger.info(f"  Tiến độ: {i}/{total_files} files...")

    # ── XML Cleaning ──────────────────────────────
    logger.info("Đang clean AndroidManifest.xml và layout XML...")
    manifest_path = decompiled_dir / "AndroidManifest.xml"
    xml_removed   = xml_cleaner.clean_manifest(manifest_path, dry_run=dry_run)
    res_dir       = decompiled_dir / "res"
    xml_removed  += xml_cleaner.clean_layout_xmls(res_dir, dry_run=dry_run)

    report = {
        "files_scanned":          total_files,
        "files_modified":         files_modified,
        "ads_methods_blocked":    total_ads_blocked,
        "store_redirects_blocked": total_store_blocked,
        "xml_entries_removed":    xml_removed,
    }

    logger.info(
        f"Hoàn thành cleaning: "
        f"{total_ads_blocked} ads blocked, "
        f"{total_store_blocked} store redirects blocked, "
        f"{xml_removed} XML entries removed."
    )

    return report
