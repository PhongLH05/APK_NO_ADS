"""
tests/test_cleaner.py — Unit tests cho module cleaner.py
Chạy: pytest tests/ -v
"""

import sys
from pathlib import Path

# Thêm parent dir vào path để import được các module
sys.path.insert(0, str(Path(__file__).parent.parent))

from cleaner import SmaliMethodParser, AdsBlocker, StoreRedirectBlocker, XMLCleaner


# ─────────────────────────────────────────────
# Fixtures — Smali code mẫu
# ─────────────────────────────────────────────

SMALI_VOID_METHOD = """\
.class public Lcom/example/AdHelper;
.super Ljava/lang/Object;

.method public loadAd(Lcom/google/android/gms/ads/AdRequest;)V
    .registers 2
    invoke-virtual {p0, p1}, Lcom/google/android/gms/ads/AdView;->loadAd(Lcom/google/android/gms/ads/AdRequest;)V
    return-void
.end method
"""

SMALI_BOOL_METHOD = """\
.method public isAdLoaded()Z
    .registers 2
    const/4 v0, 0x1
    return v0
.end method
"""

SMALI_STORE_REDIRECT = """\
.method public openPlayStore()V
    .registers 2
    const-string v0, "market://details?id=com.example.app"
    invoke-virtual {p0, v0}, Landroid/content/Intent;->setData(Landroid/net/Uri;)V
    return-void
.end method
"""

SMALI_ALREADY_BLOCKED = """\
.method public loadAd(Lcom/google/android/gms/ads/AdRequest;)V
    .registers 2
    # [APK_CLEANER] blocked
    return-void
    invoke-virtual {p0, p1}, Lcom/google/android/gms/ads/AdView;->loadAd(Lcom/google/android/gms/ads/AdRequest;)V
    return-void
.end method
"""

SMALI_MULTIPLE_METHODS = """\
.method public doSomething()V
    .registers 1
    return-void
.end method

.method public loadAd(Lcom/google/android/gms/ads/AdRequest;)V
    .registers 2
    invoke-virtual {p0, p1}, Lcom/google/android/gms/ads/AdView;->loadAd(Lcom/google/android/gms/ads/AdRequest;)V
    return-void
.end method

.method public anotherMethod()I
    .registers 2
    const/4 v0, 0x0
    return v0
.end method
"""


# ─────────────────────────────────────────────
# Tests: SmaliMethodParser
# ─────────────────────────────────────────────
class TestSmaliMethodParser:
    def test_parse_single_void_method(self):
        lines   = SMALI_VOID_METHOD.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        # Có đúng 1 method
        assert len(methods) == 1
        m = methods[0]
        assert "loadAd" in m.signature
        assert m.return_type == "V"

    def test_parse_bool_method(self):
        lines   = SMALI_BOOL_METHOD.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert len(methods) == 1
        assert methods[0].return_type == "Z"

    def test_parse_multiple_methods(self):
        lines   = SMALI_MULTIPLE_METHODS.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert len(methods) == 3

    def test_return_type_object(self):
        smali = ".method public getObject()Ljava/lang/Object;\n    return-object v0\n.end method\n"
        lines = smali.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert methods[0].return_type == "L"

    def test_return_type_array(self):
        smali = ".method public getBytes()[B\n    return-object v0\n.end method\n"
        lines = smali.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert methods[0].return_type == "["

    def test_empty_file(self):
        methods = SmaliMethodParser.parse([])
        assert methods == []

    def test_no_methods(self):
        lines = [".class public Lcom/example/Foo;\n", ".super Ljava/lang/Object;\n"]
        methods = SmaliMethodParser.parse(lines)
        assert methods == []


# ─────────────────────────────────────────────
# Tests: AdsBlocker
# ─────────────────────────────────────────────
class TestAdsBlocker:
    PATTERNS = {
        "sdk_packages": ["com/google/android/gms/ads"],
        "method_names": ["loadAd"],
        "class_keywords": ["AdView"],
    }

    def get_blocker(self):
        return AdsBlocker(self.PATTERNS)

    def test_detect_ads_method_by_body(self):
        blocker = self.get_blocker()
        lines   = SMALI_VOID_METHOD.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert blocker._is_ads_related(methods[0], SMALI_VOID_METHOD)

    def test_skip_already_blocked(self):
        blocker = self.get_blocker()
        lines   = SMALI_ALREADY_BLOCKED.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert blocker._already_blocked(methods[0])

    def test_early_return_void(self):
        blocker = self.get_blocker()
        ret     = blocker._build_early_return("V")
        assert any("return-void" in r for r in ret)

    def test_early_return_bool(self):
        blocker = self.get_blocker()
        ret     = blocker._build_early_return("Z")
        assert any("const/4" in r for r in ret)
        assert any("return v0" in r for r in ret)

    def test_early_return_object(self):
        blocker = self.get_blocker()
        ret     = blocker._build_early_return("L")
        assert any("return-object" in r for r in ret)

    def test_early_return_wide(self):
        blocker = self.get_blocker()
        ret     = blocker._build_early_return("D")
        assert any("return-wide" in r for r in ret)

    def test_process_file_dry_run(self, tmp_path):
        """Dry run không được ghi file."""
        f = tmp_path / "Test.smali"
        f.write_text(SMALI_VOID_METHOD, encoding="utf-8")
        original = f.read_text(encoding="utf-8")

        blocker = self.get_blocker()
        count   = blocker.process_file(f, dry_run=True)
        assert count == 1
        assert f.read_text(encoding="utf-8") == original  # file không đổi

    def test_process_file_writes_when_not_dry_run(self, tmp_path):
        """Không dry run → file phải bị ghi lại."""
        f = tmp_path / "Test.smali"
        f.write_text(SMALI_VOID_METHOD, encoding="utf-8")

        blocker = self.get_blocker()
        count   = blocker.process_file(f, dry_run=False)
        assert count == 1
        new_content = f.read_text(encoding="utf-8")
        assert "APK_CLEANER" in new_content
        assert "return-void" in new_content


# ─────────────────────────────────────────────
# Tests: StoreRedirectBlocker
# ─────────────────────────────────────────────
class TestStoreRedirectBlocker:
    PATTERNS = {
        "uri_patterns": [r"market://details\?id=", r"play\.google\.com/store"],
        "rate_us_keywords": ["openPlayStore", "goToPlayStore"],
    }

    def get_blocker(self):
        return StoreRedirectBlocker(self.PATTERNS)

    def test_detect_market_uri(self):
        blocker = self.get_blocker()
        lines   = SMALI_STORE_REDIRECT.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert blocker._method_has_store_redirect(methods[0])

    def test_detect_rate_us_keyword(self):
        blocker = self.get_blocker()
        smali = """\
.method public openPlayStore()V
    .registers 1
    return-void
.end method
"""
        lines   = smali.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert blocker._method_has_store_redirect(methods[0])

    def test_no_false_positive(self):
        blocker = self.get_blocker()
        smali = """\
.method public normalMethod()V
    .registers 1
    const-string v0, "Hello World"
    return-void
.end method
"""
        lines   = smali.splitlines(keepends=True)
        methods = SmaliMethodParser.parse(lines)
        assert not blocker._method_has_store_redirect(methods[0])

    def test_process_file_blocks_redirect(self, tmp_path):
        f = tmp_path / "StoreHelper.smali"
        f.write_text(SMALI_STORE_REDIRECT, encoding="utf-8")

        blocker = self.get_blocker()
        count   = blocker.process_file(f, dry_run=False)
        assert count == 1
        content = f.read_text(encoding="utf-8")
        assert "APK_CLEANER" in content


# ─────────────────────────────────────────────
# Tests: XMLCleaner
# ─────────────────────────────────────────────
class TestXMLCleaner:
    SDK_PACKAGES = ["com/google/android/gms/ads", "com/facebook/ads"]

    MANIFEST_CONTENT = """\
<?xml version="1.0" encoding="utf-8"?>
<manifest>
    <application>
        <activity android:name=".MainActivity"/>
        <activity android:name="com.google.android.gms.ads.AdActivity"/>
        <meta-data android:name="com.google.android.gms.ads.APPLICATION_ID" android:value="ca-app-pub-xxx"/>
    </application>
</manifest>
"""

    LAYOUT_CONTENT = """\
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout>
    <TextView android:text="Hello"/>
    <com.google.android.gms.ads.AdView android:id="@+id/adView"/>
</LinearLayout>
"""

    def test_clean_manifest_comments_out_ads(self, tmp_path):
        manifest = tmp_path / "AndroidManifest.xml"
        manifest.write_text(self.MANIFEST_CONTENT, encoding="utf-8")

        cleaner = XMLCleaner(self.SDK_PACKAGES)
        removed = cleaner.clean_manifest(manifest, dry_run=False)

        assert removed > 0
        content = manifest.read_text(encoding="utf-8")
        assert "<!-- [APK_CLEANER]" in content
        assert "<activity android:name=\".MainActivity\"/>" in content  # không bị ảnh hưởng

    def test_clean_manifest_dry_run(self, tmp_path):
        manifest = tmp_path / "AndroidManifest.xml"
        manifest.write_text(self.MANIFEST_CONTENT, encoding="utf-8")
        original = self.MANIFEST_CONTENT

        cleaner = XMLCleaner(self.SDK_PACKAGES)
        removed = cleaner.clean_manifest(manifest, dry_run=True)

        assert removed > 0
        assert manifest.read_text(encoding="utf-8") == original

    def test_clean_layout_xmls(self, tmp_path):
        res_dir    = tmp_path / "res"
        layout_dir = res_dir / "layout"
        layout_dir.mkdir(parents=True)

        layout_file = layout_dir / "activity_main.xml"
        layout_file.write_text(self.LAYOUT_CONTENT, encoding="utf-8")

        cleaner = XMLCleaner(self.SDK_PACKAGES)
        removed = cleaner.clean_layout_xmls(res_dir, dry_run=False)

        assert removed > 0
        content = layout_file.read_text(encoding="utf-8")
        assert "<!-- [APK_CLEANER]" in content
        assert "<TextView" in content  # giữ nguyên element không liên quan

    def test_missing_manifest_returns_zero(self, tmp_path):
        cleaner = XMLCleaner(self.SDK_PACKAGES)
        removed = cleaner.clean_manifest(tmp_path / "nonexistent.xml", dry_run=False)
        assert removed == 0
